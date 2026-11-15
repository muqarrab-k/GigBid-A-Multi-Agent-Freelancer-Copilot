"""Lightweight worker: an in-process loop that scouts saved searches and starts bid runs.

Idempotent per job: a job already in the inbox is not added twice, and a job whose thread
(job + user) exists never gets a second run. One process only; a real deployment would move
this loop to a queue worker without changing the calls.
"""

import asyncio
import logging
from typing import Any

from langgraph.store.base import BaseStore

from agent.nodes.common import ToolBox
from agent.nodes.scout import SeenStore, scout
from apps.api.core import INBOX, AppState, new_trace

log = logging.getLogger(__name__)


def bid_thread_id(job_id: str, username: str) -> str:
    return f"{job_id}:{username}"


def job_record(view: dict[str, Any]) -> dict[str, Any]:
    """Marketplace job view -> the job dict the bid graph reads."""
    text = view.get("untrusted_text")
    body = text["text"] if isinstance(text, dict) else str(text or "")
    title, _, description = body.partition("\n\n")
    return {**{k: v for k, v in view.items() if k not in ("untrusted_text", "untrusted_screening_questions")},
            "title": title, "description": description,
            "screening_questions": [q["text"] for q in view.get("untrusted_screening_questions", [])]}


async def inbox(store: BaseStore, username: str) -> dict[str, dict[str, Any]]:
    items = await store.asearch((INBOX, username), limit=1000)
    return {i.key: i.value for i in items}


async def fetch_job(state: AppState, user: dict[str, Any], job_id: str) -> dict[str, Any] | None:
    saved = await state.store.aget((INBOX, user["username"]), job_id)
    if saved:
        return saved.value
    out = await ToolBox(await state.context(user), "scout").call("get_job", {"job_id": job_id})
    return job_record(out["job"]) if out.get("ok", True) and out.get("job") else None


async def start_run(state: AppState, user: dict[str, Any], job: dict[str, Any]) -> tuple[str, str, bool]:
    """(thread_id, trace_id, started); never two runs for one job and user."""
    thread_id = bid_thread_id(job["job_id"], user["username"])
    known = await state.thread(user["username"], thread_id)
    if known:
        return thread_id, known["trace_id"], False
    trace_id = new_trace()
    await state.register(user["username"], thread_id, "bid", job_id=job["job_id"], trace_id=trace_id)
    payload = {"job": job, "thread_id": thread_id, "persona": user["persona"]}
    # before the task runs, so a listener never misses the start
    state.hub.start(thread_id)
    state.spawn(state.run_bid(user, thread_id, payload, trace_id))
    return thread_id, trace_id, True


async def scout_once(state: AppState, user: dict[str, Any], analyse: bool) -> tuple[list[str], list[str]]:
    ctx = await state.context(user)
    seen = SeenStore(state.settings.scout.seen_store.parent / f"api_{user['username']}.sqlite")
    found = await scout(ctx, seen)
    known = await inbox(state.store, user["username"])
    new, started = [], []
    for job in found:
        if job["job_id"] in known:
            continue
        await state.store.aput((INBOX, user["username"]), job["job_id"], job)
        new.append(job["job_id"])
        if analyse:
            thread_id, _, fresh = await start_run(state, user, job)
            if fresh:
                started.append(thread_id)
    return new, started


async def loop(state: AppState) -> None:
    cfg = state.settings.api.scheduler
    while True:
        for item in await state.store.asearch(("users",), limit=1000):
            try:
                await scout_once(state, item.value, cfg.analyse_new)
            except Exception as err:  # noqa: BLE001
                log.warning("scout failed for %s: %s", item.key, err)
        await asyncio.sleep(cfg.interval_minutes * 60)
