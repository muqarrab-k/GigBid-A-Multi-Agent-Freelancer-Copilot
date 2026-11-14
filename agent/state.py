from operator import add
from typing import Annotated, Any, Literal, TypedDict

from agent.handoffs import (
    Approval,
    BidDecision,
    ClaimCheck,
    ClientIntent,
    ComplianceVerdict,
    Critique,
    EvidenceItem,
    FitReport,
    InterviewSlot,
    JobSpec,
    Outcome,
    PriceQuote,
    ProposalDraft,
    RiskReport,
)

BidStatus = Literal[
    "new",
    "analysing",
    "skipped",
    "watching",
    "drafting",
    "awaiting_approval",
    "approved",
    "rejected",
    "submitted",
    "needs_attention",
    "dead_letter",
]
ConversationStatus = Literal[
    "new",
    "drafting",
    "awaiting_approval",
    "sent",
    "closed",
    "needs_attention",
    "dead_letter",
]


class TraceEvent(TypedDict):
    node: str
    kind: str
    data: dict[str, Any]


class ThreadMessage(TypedDict):
    message_id: str
    sender: Literal["client", "freelancer"]
    text: str
    sent_at: str


def merge_evidence(left: list[EvidenceItem], right: list[EvidenceItem]) -> list[EvidenceItem]:
    """Union by evidence_id, newer wins."""
    merged = {item.evidence_id: item for item in left}
    for item in right:
        merged[item.evidence_id] = item
    return list(merged.values())


def merge_messages(left: list[ThreadMessage], right: list[ThreadMessage]) -> list[ThreadMessage]:
    """Append unseen messages only."""
    seen = {msg["message_id"] for msg in left}
    return left + [msg for msg in right if msg["message_id"] not in seen]


class BidState(TypedDict, total=False):
    thread_id: str
    job: dict[str, Any]
    job_spec: JobSpec
    risk_report: RiskReport
    fit_report: FitReport
    evidence: Annotated[list[EvidenceItem], merge_evidence]
    decision: BidDecision
    price_quote: PriceQuote
    draft: ProposalDraft
    claim_checks: list[ClaimCheck]
    critiques: Annotated[list[Critique], add]
    compliance: ComplianceVerdict
    approval: Approval
    outcome: Outcome
    status: BidStatus
    # summed across branches
    step_count: Annotated[int, add]
    token_count: Annotated[int, add]
    errors: Annotated[list[str], add]
    trace: Annotated[list[TraceEvent], add]


class ConversationState(TypedDict, total=False):
    thread_id: str
    client_id: str
    job_id: str
    messages: Annotated[list[ThreadMessage], merge_messages]
    intent: ClientIntent
    draft_reply: str
    proposed_slots: list[InterviewSlot]
    approval: Approval
    status: ConversationStatus
    step_count: Annotated[int, add]
    token_count: Annotated[int, add]
    errors: Annotated[list[str], add]
    trace: Annotated[list[TraceEvent], add]
