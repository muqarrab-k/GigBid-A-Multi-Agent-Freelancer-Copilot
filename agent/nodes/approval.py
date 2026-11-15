"""Human approval gate: dry-run preview, interrupt, then edit, reject or submit."""

import difflib
import hashlib
from typing import Any

from langgraph.runtime import Runtime
from langgraph.types import interrupt

from agent.handoffs import Approval, ProposalDraft
from agent.nodes.common import BidContext, ToolBox
from agent.state import BidState
from rag.verify import TAG_RE

PAYLOAD_KEYS = ["thread_id", "job_id", "draft", "claims", "risk_report", "price", "preview", "notes"]


def plain(text: str) -> str:
    """What the client sees: no evidence tags."""
    return TAG_RE.sub("", text).strip()


def idempotency_key(state: BidState) -> str:
    draft, quote = state["draft"], state["price_quote"]
    digest = hashlib.sha256(f"{draft.cover_letter}|{draft.screening_answers}|{quote.amount}".encode()).hexdigest()
    return f"{state['thread_id']}:{digest[:16]}"


def draft_args(state: BidState) -> dict[str, Any]:
    draft = state["draft"]
    return {"job_id": draft.job_id, "cover_letter": plain(draft.cover_letter),
            "bid_amount": state["price_quote"].amount,
            "screening_answers": [plain(a) for a in draft.screening_answers],
            "idempotency_key": idempotency_key(state)}


def claim_table(state: BidState) -> list[dict[str, Any]]:
    checks = {c.claim_id: c for c in state.get("claim_checks", [])}
    texts = state.get("evidence_texts") or {}
    rows = []
    for claim in state["draft"].claims:
        check = checks.get(claim.claim_id)
        rows.append({"claim": claim.text, "evidence_ids": claim.evidence_ids,
                     "label": check.label if check else "unchecked",
                     "evidence": {i: texts.get(i, "")[:300] for i in claim.evidence_ids}})
    return rows


def down(out: dict[str, Any]) -> bool:
    return out.get("error") == "marketplace_down"


async def prepare_approval(state: BidState, runtime: Runtime[BidContext]) -> dict[str, Any]:
    """Everything the human needs, with dry runs; nothing is written."""
    tools = ToolBox(runtime.context, "approval")
    args = draft_args(state)
    preview = await tools.call("create_proposal_draft", {**args, "dry_run": True})
    balance = await tools.call("get_connects_balance", {})
    if down(preview) or down(balance):
        return {"status": "queued", "errors": ["marketplace unavailable before approval; queued"],
                "trace": tools.events, "step_count": 1}
    check = preview.get("policy_check") or {}
    if check and check.get("passed") is False:
        # the platform would refuse it; never ask a human to approve that
        return {"status": "blocked", "trace": tools.events, "step_count": 1,
                "errors": [f"marketplace policy check failed: {check.get('rule_id')} {check.get('detail', '')}".strip()]}
    cost = preview.get("connects_cost") or state["price_quote"].connects_cost
    have = (balance.get("connects") or {}).get("balance")
    report = state.get("verification")
    payload = {
        "thread_id": state["thread_id"], "job_id": state["draft"].job_id,
        "draft": {"cover_letter": args["cover_letter"], "screening_answers": args["screening_answers"],
                  "with_tags": state["draft"].cover_letter, "revision": state["draft"].revision},
        "claims": claim_table(state),
        "risk_report": state["risk_report"].model_dump() if state.get("risk_report") else None,
        "price": state["price_quote"].model_dump(),
        "preview": {"create_proposal_draft": {"dry_run": True, "connects_cost": cost,
                                              "policy_check": preview.get("policy_check")},
                    "submit_proposal": {"dry_run": True, "connects_cost": cost, "balance_before": have,
                                        "balance_after": have - cost if have is not None else None}},
        "notes": {"verifier": report.model_dump() if report else None,
                  "critic": [c.model_dump() for c in state.get("critiques", [])][-1:],
                  "compliance": state["compliance"].model_dump() if state.get("compliance") else None,
                  "other": state.get("notes", [])},
    }
    return {"approval_preview": payload, "status": "awaiting_approval", "trace": tools.events, "step_count": 1}


def approval_gate(state: BidState) -> dict[str, Any]:
    """Pause for the human. Resume with Command(resume={'action': ...})."""
    answer = interrupt(state["approval_preview"])
    approval = answer if isinstance(answer, Approval) else Approval.model_validate(answer)
    return {"approval": approval, "step_count": 1,
            "trace": [{"node": "approval_gate", "kind": "human", "data": approval.model_dump()}]}


def after_gate(state: BidState) -> str:
    return {"approve": "submit", "edit": "apply_edit", "reject": "reject"}[state["approval"].action]


def apply_edit(state: BidState) -> dict[str, Any]:
    """Swap in the human's text and keep the diff for style memory."""
    old, new = state["draft"], state["approval"].edited_text or ""
    diff = "\n".join(difflib.unified_diff(plain(old.cover_letter).splitlines(), new.splitlines(),
                                          "draft", "edited", lineterm=""))
    paragraphs = [p.strip() for p in new.split("\n\n") if p.strip()]
    draft = ProposalDraft(job_id=old.job_id, paragraphs=paragraphs, screening_answers=old.screening_answers,
                          evidence_ids=old.evidence_ids, revision=old.revision)
    return {"draft": draft, "status": "drafting", "step_count": 1,
            "pending_edits": [{"thread_id": state["thread_id"], "job_id": old.job_id, "diff": diff,
                               "before": plain(old.cover_letter), "after": new}]}


def reject(state: BidState) -> dict[str, Any]:
    reason = state["approval"].reason or "no reason given"
    return {"status": "rejected", "submission": {"outcome": "rejected", "reason": reason},
            "draft": state["draft"].model_copy(update={"status": "rejected"}), "step_count": 1}


async def submit(state: BidState, runtime: Runtime[BidContext]) -> dict[str, Any]:
    """Only reached after an approve; the same key makes a resume safe."""
    if state.get("approval") is None or state["approval"].action != "approve":
        raise PermissionError("submit needs a human approval")
    tools = ToolBox(runtime.context, "approval")
    args = draft_args(state)
    created = await tools.call("create_proposal_draft", args)
    if down(created) or not created.get("ok", True) or not created.get("proposal"):
        return {"status": "queued" if down(created) else "needs_attention", "trace": tools.events, "step_count": 1,
                "errors": [f"create_proposal_draft: {created.get('error')} {created.get('detail', '')}".strip()]}
    proposal_id = created["proposal"]["proposal_id"]
    sent = await tools.call("submit_proposal", {"proposal_id": proposal_id,
                                                 "idempotency_key": f"{args['idempotency_key']}:submit"})
    if down(sent) or not sent.get("ok", True):
        return {"status": "queued" if down(sent) else "needs_attention", "trace": tools.events, "step_count": 1,
                "errors": [f"submit_proposal: {sent.get('error')} {sent.get('detail', '')}".strip()]}
    return {"status": "submitted", "trace": tools.events, "step_count": 1,
            "draft": state["draft"].model_copy(update={"status": "sent"}),
            "submission": {"proposal_id": proposal_id, "idempotency_key": args["idempotency_key"],
                           "connects_spent": sent.get("connects_cost"), "balance_after": sent.get("balance_after")}}
