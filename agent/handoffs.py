from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RiskFlag = Literal[
    "scam",
    "unpaid_work",
    "off_platform",
    "injection",
    "low_budget",
    "payment_unverified",
    "poor_client_history",
    "vague_scope",
]
IntentLabel = Literal["question", "negotiation", "interview_request", "scam_signal"]
Outcome = Literal["won", "replied", "viewed", "ignored", "lost"]

Score = Annotated[float, Field(ge=0, le=1)]


class Handoff(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class JobSpec(Handoff):
    job_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    client_id: str | None = None
    deliverables: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    requirements: list[str] = Field(default_factory=list)
    budget_min: float | None = Field(default=None, ge=0)
    budget_max: float | None = Field(default=None, ge=0)
    timeline_days: int | None = Field(default=None, ge=0, le=730)
    screening_questions: list[str] = Field(default_factory=list)
    hidden_needs: list[str] = Field(default_factory=list)
    connects_cost: int = Field(default=0, ge=0, le=100)

    @model_validator(mode="after")
    def check_budget(self) -> "JobSpec":
        if self.budget_min is not None and self.budget_max is not None:
            if self.budget_max < self.budget_min:
                raise ValueError("budget_max is below budget_min")
        return self


class RiskReport(Handoff):
    score: Score
    client_quality: Score | None = None
    flags: list[RiskFlag] = Field(default_factory=list)
    injection_detected: bool = False
    explanation: str = Field(min_length=1)
    # rules and model signals that fired
    signals: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def sync_flags(self) -> "RiskReport":
        # dedupe, keep order
        self.flags = list(dict.fromkeys(self.flags))
        if self.injection_detected and "injection" not in self.flags:
            self.flags.append("injection")
        if "injection" in self.flags:
            self.injection_detected = True
        return self


class EvidenceItem(Handoff):
    evidence_id: str = Field(min_length=1)
    type: str
    source: str
    text: str
    date: str | None = None
    outcome: Outcome | None = None
    score: float | None = None


class RequirementMatch(Handoff):
    requirement: str = Field(min_length=1)
    strength: Literal["strong", "partial", "none"]
    evidence_ids: list[str] = Field(default_factory=list)
    note: str = ""

    @model_validator(mode="after")
    def check_evidence(self) -> "RequirementMatch":
        if self.strength != "none" and not self.evidence_ids:
            raise ValueError(f"'{self.strength}' match needs evidence_ids")
        if self.strength == "none" and self.evidence_ids:
            raise ValueError("'none' match cannot cite evidence")
        return self


class FitReport(Handoff):
    score: Score
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    matrix: list[RequirementMatch] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def collect_evidence(self) -> "FitReport":
        # collect matrix ids
        ids = list(self.evidence_ids)
        for row in self.matrix:
            ids.extend(row.evidence_ids)
        self.evidence_ids = list(dict.fromkeys(ids))
        return self


class BidDecision(Handoff):
    job_id: str = Field(min_length=1)
    action: Literal["skip", "watch", "bid"]
    reasons: list[str] = Field(min_length=1)


class PriceQuote(Handoff):
    amount: float = Field(gt=0)
    billing: Literal["fixed", "hourly"]
    currency: str = "USD"
    rationale: str = Field(min_length=1)
    connects_cost: int = Field(ge=0, le=100)
    connects_worth_it: bool


class Claim(Handoff):
    claim_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)


class ClaimCheck(Handoff):
    claim_id: str = Field(min_length=1)
    label: Literal["supported", "partly", "unsupported"]
    evidence_ids: list[str] = Field(default_factory=list)
    note: str = ""

    @model_validator(mode="after")
    def check_evidence(self) -> "ClaimCheck":
        if self.label != "unsupported" and not self.evidence_ids:
            raise ValueError(f"'{self.label}' claim needs evidence_ids")
        return self


class ProposalDraft(Handoff):
    job_id: str = Field(min_length=1)
    cover_letter: str = ""
    paragraphs: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    screening_answers: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    revision: int = Field(default=0, ge=0, le=10)
    status: Literal["pending_review", "approved", "rejected", "sent"] = "pending_review"

    @model_validator(mode="after")
    def check_draft(self) -> "ProposalDraft":
        # sync paragraphs
        if self.paragraphs and not self.cover_letter:
            self.cover_letter = "\n\n".join(self.paragraphs)
        elif self.cover_letter and not self.paragraphs:
            self.paragraphs = [p.strip() for p in self.cover_letter.split("\n\n") if p.strip()]
        if not self.cover_letter:
            raise ValueError("draft needs cover_letter or paragraphs")

        known = set(self.evidence_ids)
        for claim in self.claims:
            unknown = set(claim.evidence_ids) - known
            if unknown:
                raise ValueError(f"claim {claim.claim_id} cites unknown evidence {sorted(unknown)}")
        return self


class VerificationReport(Handoff):
    claims_before: int = Field(ge=0)
    unsupported_before: int = Field(ge=0)
    partly_before: int = Field(ge=0)
    removed: list[str] = Field(default_factory=list)
    claims_after: int = Field(ge=0)
    unsupported_after: int = Field(ge=0)


class Critique(Handoff):
    verdict: Literal["pass", "revise"]
    reasons: list[str] = Field(default_factory=list)
    revision_count: int = Field(default=0, ge=0, le=10)

    @model_validator(mode="after")
    def check_reasons(self) -> "Critique":
        if self.verdict == "revise" and not self.reasons:
            raise ValueError("revise needs at least one reason")
        return self


class ComplianceVerdict(Handoff):
    verdict: Literal["allowed", "blocked"]
    violations: list[str] = Field(default_factory=list)
    cleaned_text: str = ""

    @model_validator(mode="after")
    def check_violations(self) -> "ComplianceVerdict":
        if self.verdict == "blocked" and not self.violations:
            raise ValueError("blocked verdict needs violations")
        return self


class ClientIntent(Handoff):
    intent: IntentLabel
    confidence: Score
    summary: str = ""


class InterviewSlot(Handoff):
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def check_order(self) -> "InterviewSlot":
        if self.end <= self.start:
            raise ValueError("slot end must be after start")
        return self


class Approval(Handoff):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def check_action(self) -> "Approval":
        if self.action == "edit" and not self.edited_text:
            raise ValueError("edit needs edited_text")
        if self.action == "reject" and not self.reason:
            raise ValueError("reject needs a reason")
        return self
