"""Claim verification node: drop unsupported claims before the Critic sees the draft."""

from typing import Any, Literal

from langgraph.runtime import Runtime
from pydantic import BaseModel

from agent.handoffs import Claim
from agent.nodes.common import BidContext, ToolBox, structured, tokens_used
from agent.state import BidState
from rag.verify import split_claims, verify_draft


class JudgeOut(BaseModel):
    label: Literal["supported", "partly", "unsupported"]
    reason: str = ""


def editing(state: BidState) -> bool:
    approval = state.get("approval")
    return bool(approval and approval.action == "edit")


async def verifier(state: BidState, runtime: Runtime[BidContext]) -> dict[str, Any]:
    ctx, draft = runtime.context, state["draft"]
    texts = dict(state.get("evidence_texts") or {})
    tools = ToolBox(ctx, "verifier")
    for claim in split_claims(draft):
        for eid in claim.evidence_ids:
            if eid not in texts:
                found = await tools.call("get_evidence", {"evidence_id": eid})
                if found.get("ok") and found.get("evidence"):
                    texts[eid] = found["evidence"]["text"]
    events: list[dict[str, Any]] = []

    async def judge(claim: Claim, evidence: str) -> tuple[str, str]:
        out, trace, _ = await structured(ctx, "verifier", JudgeOut, claim=claim.text, evidence=evidence[:3000])
        events.extend(trace)
        return (out.label, out.reason[:120]) if out else ("partly", "judge failed")

    cleaned, checks, report = await verify_draft(draft, texts, ctx.settings.verifier, judge)
    update: dict[str, Any] = {"claim_checks": checks, "verification": report, "evidence_texts": texts,
                              "trace": [*tools.events, *events], "token_count": tokens_used(events), "step_count": 1}
    if editing(state):
        # a human's words are reported on, never rewritten
        notes = [f"edited text: {report.unsupported_before} claim(s) not found in the evidence"] if report.unsupported_before else []
        return {**update, "draft": draft.model_copy(update={"claims": split_claims(draft)}), "notes": notes}
    return {**update, "draft": cleaned}
