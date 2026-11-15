"""Inbox ranked by fit, job detail, scouting and bid runs."""

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from apps.api.deps import State, User
from apps.api.scheduler import bid_thread_id, fetch_job, inbox, scout_once, start_run
from apps.api.schemas import InboxOut, JobDetail, JobRow, RunIn, RunOut, RunState, ScoutOut
from apps.api.streaming import sse

router = APIRouter(tags=["jobs"])


def dump(value: Any) -> Any:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def row(job: dict[str, Any], values: dict[str, Any], thread_id: str | None) -> JobRow:
    fit, risk, decision, quote = (values.get(k) for k in ("fit_report", "risk_report", "decision", "price_quote"))
    return JobRow(job_id=job["job_id"], title=job.get("title", ""), category=job.get("category"),
                  budget_type=job.get("budget_type"), budget_min=job.get("budget_min"),
                  budget_max=job.get("budget_max") or job.get("hourly_max"),
                  fit_score=fit.score if fit else None, risk_score=risk.score if risk else None,
                  risk_badges=list(risk.flags) if risk else [],
                  recommended_action=decision.action if decision else None,
                  price=quote.amount if quote else None, billing=quote.billing if quote else None,
                  connects_cost=quote.connects_cost if quote else job.get("connects_cost"),
                  status=values.get("status"), thread_id=thread_id)


@router.get("/jobs", response_model=InboxOut)
async def jobs_inbox(state: State, user: User) -> InboxOut:
    jobs = await inbox(state.store, user["username"])
    for t in await state.threads(user["username"], "bid"):
        if t["job_id"] not in jobs:
            values = (await state.snapshot("bid", t["thread_id"])).values
            if values.get("job"):
                jobs[t["job_id"]] = values["job"]
    rows = []
    for job_id, job in jobs.items():
        thread_id = bid_thread_id(job_id, user["username"])
        known = await state.thread(user["username"], thread_id)
        values = (await state.snapshot("bid", thread_id)).values if known else {}
        rows.append(row(job, values, thread_id if known else None))
    rows.sort(key=lambda r: (r.fit_score is None, -(r.fit_score or 0)))
    return InboxOut(items=rows)


@router.post("/jobs/scout", response_model=ScoutOut)
async def scout_now(state: State, user: User, analyse: bool = False) -> ScoutOut:
    new, started = await scout_once(state, user, analyse)
    return ScoutOut(found=len(new), new_jobs=new, runs_started=started)


@router.get("/jobs/{job_id}", response_model=JobDetail)
async def job_detail(job_id: str, state: State, user: User) -> JobDetail:
    thread_id = bid_thread_id(job_id, user["username"])
    known = await state.thread(user["username"], thread_id)
    values = (await state.snapshot("bid", thread_id)).values if known else {}
    job = values.get("job") or await fetch_job(state, user, job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    fit, quote, decision = values.get("fit_report"), values.get("price_quote"), values.get("decision")
    return JobDetail(job=job, thread_id=thread_id if known else None, status=values.get("status"),
                     job_spec=dump(values.get("job_spec")), risk_report=dump(values.get("risk_report")),
                     evidence_matrix=[dump(r) for r in fit.matrix] if fit else [],
                     price_rationale=quote.rationale if quote else None, price=dump(quote),
                     decision_reasons=decision.reasons if decision else [], notes=values.get("notes", []),
                     errors=values.get("errors", []))


@router.post("/runs", response_model=RunOut, status_code=202)
async def start(body: RunIn, state: State, user: User) -> RunOut:
    job = await fetch_job(state, user, body.job_id)
    if job is None:
        raise HTTPException(404, "no such job")
    thread_id, trace_id, started = await start_run(state, user, job)
    values = (await state.snapshot("bid", thread_id)).values
    return RunOut(thread_id=thread_id, trace_id=trace_id, status=values.get("status") or "new", started=started,
                  events_url=f"/runs/{thread_id}/events")


async def owned(state: State, user: User, thread_id: str) -> dict[str, Any]:
    known = await state.thread(user["username"], thread_id)
    if known is None:
        raise HTTPException(404, "no such run")
    return known


@router.get("/runs/{thread_id}", response_model=RunState)
async def run_state(thread_id: str, state: State, user: User) -> RunState:
    known = await owned(state, user, thread_id)
    snap = await state.snapshot(known["kind"], thread_id)
    return RunState(thread_id=thread_id, status=snap.values.get("status"), next=list(snap.next),
                    trace_id=known.get("trace_id"), errors=snap.values.get("errors", []))


@router.get("/runs/{thread_id}/events")
async def run_events(thread_id: str, state: State, user: User) -> StreamingResponse:
    """SSE: node events as they happen; a finished run replays them, then 'done'."""
    known = await owned(state, user, thread_id)

    async def stream() -> Any:
        if thread_id not in state.hub.events:
            # process restarted: one snapshot from the checkpointer
            values = (await state.snapshot(known["kind"], thread_id)).values
            yield sse({"event": "done", "status": values.get("status"), "trace_id": known.get("trace_id")})
            return
        async for event in state.hub.follow(thread_id):
            yield sse(event)
            await asyncio.sleep(0)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
