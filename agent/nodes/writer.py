"""Proposal Writer: grounded draft with evidence tags on every factual sentence."""

from typing import Any

from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from agent.handoffs import ProposalDraft
from agent.nodes.common import BidContext, ToolBox, job_text, structured, tokens_used, untrusted
from agent.profile import load_profile
from agent.state import BidState
from rag.verify import TAG_RE


class WriterOut(BaseModel):
    paragraphs: list[str] = Field(min_length=1, max_length=6)
    screening_answers: list[str] = Field(default_factory=list, max_length=10)


async def gather_evidence(ctx: BidContext, state: BidState, node: str) -> dict[str, str]:
    """Full text for the strongest evidence items."""
    texts = dict(state.get("evidence_texts") or {})
    items = sorted(state.get("evidence", []), key=lambda e: -(e.score or 0))[: ctx.settings.writer.max_evidence]
    tools = ToolBox(ctx, node)
    for item in items:
        if item.evidence_id not in texts:
            found = await tools.call("get_evidence", {"evidence_id": item.evidence_id})
            evidence = found.get("evidence") if found.get("ok") else None
            texts[item.evidence_id] = evidence["text"] if evidence else item.text
    return texts


def style_note(ctx: BidContext) -> str:
    if not ctx.style_rules:
        return ""
    return "- Style this freelancer asked for:\n" + "\n".join(f"  - {r}" for r in ctx.style_rules) + "\n"


def revision_note(state: BidState) -> str:
    critiques = state.get("critiques", [])
    report = state.get("verification")
    if not critiques or critiques[-1].verdict == "pass":
        return ""
    lines = [f"- {r}" for r in critiques[-1].reasons]
    lines += [f"- removed as unsupported: {c}" for c in (report.removed if report else [])]
    return "\nThis is a revision. Fix these points from the Critic and the claim checker:\n" + "\n".join(lines)


async def writer(state: BidState, runtime: Runtime[BidContext]) -> dict[str, Any]:
    ctx, job = runtime.context, state["job"]
    profile, quote, spec = load_profile(ctx.persona), state.get("price_quote"), state.get("job_spec")
    texts = await gather_evidence(ctx, state, "writer")
    cap = ctx.settings.writer.evidence_chars
    evidence = "\n".join(f"- [{eid}] {text[:cap]}" for eid, text in texts.items()) or "(none)"
    price = f"{quote.billing} ${quote.amount:.0f}" if quote else "use the client's budget"
    spec_text = (f"requirements: {spec.requirements}; hidden needs: {spec.hidden_needs}; "
                 f"screening questions: {spec.screening_questions}") if spec else "(not available)"
    out, events, error = await structured(
        ctx, "writer", WriterOut, name=profile.name, job=untrusted(job_text(job)), spec=spec_text,
        evidence=evidence, price=price, min_words=ctx.settings.writer.min_words,
        max_words=ctx.settings.writer.max_words, style=style_note(ctx), revision=revision_note(state))
    update: dict[str, Any] = {"trace": events, "token_count": tokens_used(events), "step_count": 1,
                              "evidence_texts": texts}
    if out is None:
        return {**update, "status": "needs_attention", "errors": [f"writer: {error}"]}
    previous = state.get("draft")
    ids = sorted({i.strip() for p in [*out.paragraphs, *out.screening_answers]
                  for m in TAG_RE.finditer(p) for i in m.group(1).split(",")})
    draft = ProposalDraft(job_id=job["job_id"], paragraphs=[p.strip() for p in out.paragraphs if p.strip()],
                          screening_answers=out.screening_answers, evidence_ids=ids,
                          revision=previous.revision + 1 if previous else 0)
    return {**update, "draft": draft, "status": "drafting"}
