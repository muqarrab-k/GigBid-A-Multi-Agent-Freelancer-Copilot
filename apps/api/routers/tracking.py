"""Proposals, pipeline from GigSim events, and analytics."""

import json
from collections import Counter
from statistics import mean
from typing import Any

from fastapi import APIRouter, HTTPException

from agent.config import ROOT
from agent.memory.store import POSITIVE, learn_from_events
from agent.nodes.common import ToolBox
from apps.api.core import INBOX, PREFS
from apps.api.deps import State, User
from apps.api.scheduler import bid_thread_id
from apps.api.schemas import AnalyticsOut, CategoryStats, PipelineOut, ProposalRow, ProposalsOut

router = APIRouter(tags=["tracking"])
RESULTS = ROOT / "evals" / "results"


async def marketplace(state: State, user: User, tool: str, args: dict[str, Any]) -> dict[str, Any]:
    out = await ToolBox(await state.context(user), "scout").call(tool, args)
    if out.get("error") == "marketplace_down":
        raise HTTPException(503, "marketplace unavailable")
    return out


async def proposal_rows(state: State, user: User) -> list[ProposalRow]:
    out = await marketplace(state, user, "list_proposals", {})
    rows = []
    for p in out.get("items", []):
        thread_id = bid_thread_id(p["job_id"], user["username"])
        known = await state.thread(user["username"], thread_id)
        rows.append(ProposalRow(proposal_id=p["proposal_id"], job_id=p["job_id"], status=p["status"],
                                bid_amount=p.get("bid_amount"), connects_cost=p.get("connects_cost"),
                                thread_id=thread_id if known else None, submitted_at=p.get("submitted_at")))
    return rows


@router.get("/proposals", response_model=ProposalsOut)
async def proposals(state: State, user: User) -> ProposalsOut:
    return ProposalsOut(items=await proposal_rows(state, user))


async def categories(state: State, user: User, job_ids: set[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    for job_id in job_ids:
        saved = await state.store.aget((INBOX, user["username"]), job_id)
        job = saved.value if saved else (await marketplace(state, user, "get_job", {"job_id": job_id})).get("job")
        found[job_id] = (job or {}).get("category") or "unknown"
    return found


@router.get("/pipeline", response_model=PipelineOut)
async def pipeline(state: State, user: User) -> PipelineOut:
    """Statuses from GigSim; new status events also feed outcome memory."""
    rows = await proposal_rows(state, user)
    cursor_item = await state.store.aget((PREFS, user["username"]), "events_cursor")
    cursor = cursor_item.value["cursor"] if cursor_item else 0
    page = await marketplace(state, user, "get_events", {"since": cursor, "limit": 50})
    events = page.get("events", [])
    job_ids = {e["data"]["job_id"] for e in events if e.get("data", {}).get("job_id")}
    promoted = await learn_from_events(state.store, user["username"], events, await categories(state, user, job_ids),
                                       state.settings)
    await state.store.aput((PREFS, user["username"]), "events_cursor", {"cursor": page.get("next_cursor", cursor)})
    return PipelineOut(counts=dict(Counter(r.status for r in rows)), proposals=rows, new_events=len(events),
                       promoted_memory=promoted)


def eval_summaries() -> list[dict[str, Any]]:
    """Proposal eval files: status counts and compliance rules, read as they are."""
    out = []
    for path in sorted(RESULTS.glob("proposals_*.json")):
        rows = json.loads(path.read_text()).get("rows", [])
        rules = Counter(v.split(":")[0] for r in rows for v in r.get("compliance_violations") or [])
        out.append({"file": str(path.relative_to(ROOT)), "proposals": len(rows),
                    "statuses": dict(Counter(r.get("status") for r in rows)), "compliance_rules": dict(rules)})
    return out


@router.get("/analytics", response_model=AnalyticsOut)
async def analytics(state: State, user: User) -> AnalyticsOut:
    rows = await proposal_rows(state, user)
    sent = [r for r in rows if r.status != "draft"]
    cats = await categories(state, user, {r.job_id for r in sent})
    by_cat: dict[str, list[ProposalRow]] = {}
    for r in sent:
        by_cat.setdefault(cats[r.job_id], []).append(r)
    stats = []
    for cat, group in sorted(by_cat.items()):
        replied = sum(r.status in POSITIVE for r in group)
        hired = sum(r.status == "hired" for r in group)
        stats.append(CategoryStats(category=cat, submitted=len(group), replied=replied, hired=hired,
                                   reply_rate=round(replied / len(group), 3), hire_rate=round(hired / len(group), 3)))
    connects: Counter[str] = Counter()
    for r in sent:
        connects[r.status] += r.connects_cost or 0
    usd, latency, reasons = [], [], Counter[str]()
    for t in await state.threads(user["username"], "bid"):
        values = (await state.snapshot("bid", t["thread_id"])).values
        llm = [e["data"] for e in values.get("trace", []) if e["kind"] == "llm"]
        if values.get("draft") and llm:
            usd.append(sum(e["usd"] for e in llm))
            latency.append(sum(e["latency_s"] for e in llm))
        if (values.get("submission") or {}).get("outcome") == "rejected":
            reasons[f"human: {values['submission']['reason']}"] += 1
        for v in (values.get("compliance").violations if values.get("compliance") else []):
            reasons[f"compliance: {v.split(':')[0]}"] += 1
    per = {"proposals": float(len(usd)), "usd_mean": round(mean(usd), 6) if usd else None,
           "llm_latency_s_mean": round(mean(latency), 2) if latency else None}
    return AnalyticsOut(by_category=stats, connects_by_outcome=dict(connects), per_proposal=per,
                        rejection_reasons=reasons.most_common(10), eval_files=eval_summaries())
