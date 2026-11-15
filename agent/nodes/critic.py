"""Critic: grounding, personalisation, opening, length and screening answers. At most N revisions."""

from typing import Any

from langgraph.runtime import Runtime

from agent.handoffs import Critique, ProposalDraft
from agent.nodes.common import BidContext
from agent.state import BidState
from rag.verify import TAG_RE, content_words, sentences


def words(draft: ProposalDraft) -> int:
    return len(TAG_RE.sub("", draft.cover_letter).split())


def review(state: BidState, ctx: BidContext) -> list[str]:
    """Reasons to revise; empty means pass."""
    draft, cfg, report = state["draft"], ctx.settings, state.get("verification")
    reasons = []
    if report and report.unsupported_before:
        reasons.append(f"{report.unsupported_before} unsupported claim(s) were removed; rebuild those points from the evidence")
    if report and report.claims_after < 2:
        reasons.append("fewer than 2 grounded claims; cite more of the listed evidence")
    first = sentences(draft.paragraphs[0])[0].lower() if draft.paragraphs else ""
    generic = [g for g in cfg.critic.generic_openers if g in first]
    if generic:
        reasons.append(f"generic opening ({generic[0]}); open with the client's problem")
    spec = state.get("job_spec")
    job_terms = content_words(" ".join([state["job"].get("title", ""), *(spec.requirements if spec else [])]))
    used = job_terms & content_words(draft.paragraphs[0] if draft.paragraphs else "")
    if len(used) < cfg.critic.min_job_terms:
        reasons.append("first paragraph does not use the job's specifics")
    n = words(draft)
    if not cfg.writer.min_words <= n <= cfg.writer.max_words:
        reasons.append(f"{n} words, keep it between {cfg.writer.min_words} and {cfg.writer.max_words}")
    questions = state["job"].get("screening_questions") or []
    answers = draft.screening_answers
    if len(answers) < len(questions) or any(len(a.split()) < 8 for a in answers[: len(questions)]):
        reasons.append(f"answer all {len(questions)} screening question(s) in full sentences")
    return reasons


async def critic(state: BidState, runtime: Runtime[BidContext]) -> dict[str, Any]:
    ctx, draft = runtime.context, state["draft"]
    reasons = review(state, ctx)
    critique = Critique(verdict="revise" if reasons else "pass", reasons=reasons, revision_count=draft.revision)
    best = state.get("best_draft")
    best_reasons = next((len(c.reasons) for c in reversed(state.get("critiques", []))
                         if best and c.revision_count == best.revision), None)
    update: dict[str, Any] = {"critiques": [critique], "step_count": 1,
                              "trace": [{"node": "critic", "kind": "critique",
                                         "data": {"verdict": critique.verdict, "reasons": reasons}}]}
    if best is None or best_reasons is None or len(reasons) < best_reasons:
        update["best_draft"] = draft
    if reasons and draft.revision >= ctx.settings.budgets.max_revisions:
        # out of revisions: continue with the best draft, visibly
        update["draft"] = update.get("best_draft", best) or draft
        update["notes"] = [f"critic_unresolved: {'; '.join(reasons)}"]
    return update


def after_critic(state: BidState, runtime: Runtime[BidContext]) -> str:
    last = state["critiques"][-1]
    # the reviewed revision, not the best draft swapped in
    if last.verdict == "revise" and last.revision_count < runtime.context.settings.budgets.max_revisions:
        return "writer"
    return "compliance"

