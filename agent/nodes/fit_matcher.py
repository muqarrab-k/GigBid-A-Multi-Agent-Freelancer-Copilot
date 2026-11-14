"""Fit Matcher: requirement-to-evidence matrix and fit score. Runs beside the analyst."""

import re
from typing import Any

from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from agent.handoffs import EvidenceItem, FitReport, RequirementMatch
from agent.nodes.common import BidContext, ToolBox, job_text, structured, tokens_used, untrusted
from agent.profile import load_profile
from agent.state import BidState

WEIGHT = {"strong": 1.0, "partial": 0.5, "none": 0.0}


class RequirementsOut(BaseModel):
    requirements: list[str] = Field(min_length=1, max_length=8)


def gaps_in(text: str, gaps: list[str]) -> list[str]:
    low = text.lower()
    return [g for g in gaps if re.search(rf"(?<![a-z0-9]){re.escape(g.lower())}(?![a-z0-9])", low)]


async def fit_matcher(state: BidState, runtime: Runtime[BidContext]) -> dict[str, Any]:
    ctx, job = runtime.context, state["job"]
    cfg = ctx.settings.fit
    text = job_text(job)
    out, events, error = await structured(ctx, "fit_matcher", RequirementsOut, job=untrusted(text),
                                          max_requirements=cfg.max_requirements)
    update: dict[str, Any] = {"trace": events, "token_count": tokens_used(events), "step_count": 1}
    if out is None:
        return {**update, "failed": ["fit_report"], "errors": [f"fit_matcher: {error}"]}

    tools = ToolBox(ctx, "fit_matcher")
    rows, evidence, seen = [], [], set()
    for requirement in list(dict.fromkeys(out.requirements))[: cfg.max_requirements]:
        found = await tools.call("search_evidence", {"requirement": requirement, "k": cfg.k_per_requirement})
        items = found.get("items", []) if found.get("ok") else []
        best = items[0]["score"] if items else 0.0
        strength = "strong" if best >= cfg.strong_score else "partial" if best >= cfg.partial_score else "none"
        ids = [i["evidence_id"] for i in items if i["score"] >= cfg.partial_score] if strength != "none" else []
        rows.append(RequirementMatch(requirement=requirement[:200], strength=strength, evidence_ids=ids,
                                     note=f"best score {best:.2f}"))
        evidence += [i for i in items if i["evidence_id"] in ids and i["evidence_id"] not in seen]
        seen.update(ids)

    gaps = gaps_in(text, load_profile(ctx.persona).gaps)
    raw = sum(WEIGHT[r.strength] for r in rows) / len(rows)
    score = max(0.0, min(1.0, raw - cfg.gap_penalty * len(gaps)))
    reasons = [f"{sum(r.strength == s for r in rows)} {s}" for s in ("strong", "partial", "none")]
    reasons += [f"persona gap: {g}" for g in gaps]
    report = FitReport(score=round(score, 3), matched_skills=[r.requirement for r in rows if r.strength != "none"],
                       missing_skills=[r.requirement for r in rows if r.strength == "none"] + gaps,
                       matrix=rows, reasons=reasons)
    items = [EvidenceItem(evidence_id=i["evidence_id"], type=i["type"], source=i["source"], text=i["snippet"],
                          date=i.get("date"), outcome=i.get("outcome"), score=i["score"]) for i in evidence]
    return {**update, "fit_report": report, "evidence": items, "trace": [*events, *tools.events]}
