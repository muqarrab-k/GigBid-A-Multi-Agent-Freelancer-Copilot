"""Long-term memory in a LangGraph store: style rules from edits, outcomes per job category."""

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from langgraph.store.base import BaseStore
from langgraph.store.memory import InMemoryStore
from langgraph.store.postgres.aio import AsyncPostgresStore

from agent.config import Settings, get_config
from agent.graphs.checkpoint import postgres_dsn
from agent.memory.promotion_rules import edit_patterns, should_promote, should_promote_outcome

STYLE, EDITS, OUTCOME, PROPOSALS = "style", "style_edits", "outcome", "proposals"
KINDS = (STYLE, OUTCOME)
POSITIVE = {"replied", "interview", "hired"}
SEEN = POSITIVE | {"submitted", "viewed", "lost", "ignored"}


def ns(user: str, kind: str) -> tuple[str, ...]:
    return ("memory", user, kind)


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@asynccontextmanager
async def open_store(settings: Settings | None = None) -> AsyncIterator[BaseStore]:
    settings = settings or get_config()
    if settings.memory.backend == "memory":
        yield InMemoryStore()
        return
    async with AsyncPostgresStore.from_conn_string(postgres_dsn(settings)) as store:
        await store.setup()
        yield store


async def all_items(store: BaseStore, namespace: tuple[str, ...]) -> list[Any]:
    items, offset = [], 0
    while True:
        page = await store.asearch(namespace, limit=100, offset=offset)
        items += page
        if len(page) < 100:
            return items
        offset += 100


async def learn_from_edits(store: BaseStore, user: str, edits: list[dict[str, Any]],
                           settings: Settings | None = None) -> list[str]:
    """Record each edit's patterns; promote the ones that now pass the rule."""
    cfg = (settings or get_config()).memory.style
    for edit in edits:
        found, against = edit_patterns(edit.get("before", ""), edit.get("after", ""), cfg)
        key = hashlib.sha256(f"{edit.get('thread_id')}|{edit.get('diff', '')}".encode()).hexdigest()[:16]
        await store.aput(ns(user, EDITS), key, {
            "thread_id": edit.get("thread_id"), "job_id": edit.get("job_id"), "diff": edit.get("diff", ""),
            "patterns": [p.key for p in found], "rules": {p.key: p.rule for p in found},
            "against": against, "at": edit.get("at") or now()})
    history = sorted((i.value for i in await all_items(store, ns(user, EDITS))), key=lambda v: v["at"])
    promoted = []
    keys = {k for h in history for k in h["patterns"]}
    for key in sorted(keys):
        if await store.aget(ns(user, STYLE), key) or not should_promote(key, history, cfg):
            continue
        sources = [h for h in history if key in h["patterns"]]
        await store.aput(ns(user, STYLE), key, {
            "rule": sources[-1]["rules"][key],
            "why": (f"seen in {len(sources)} edits, at least {cfg.min_share:.0%} of the last {cfg.window}, "
                    f"none against (min_repeats={cfg.min_repeats})"),
            "source_edits": [{"thread_id": s["thread_id"], "job_id": s["job_id"], "diff": s["diff"]} for s in sources],
            "promoted_at": now()})
        promoted.append(key)
    return promoted


async def style_rules(store: BaseStore, user: str) -> list[str]:
    return [i.value["rule"] for i in await all_items(store, ns(user, STYLE))]


async def learn_from_events(store: BaseStore, user: str, events: list[dict[str, Any]],
                            categories: dict[str, str], settings: Settings | None = None) -> list[str]:
    """Latest status per proposal, then per category counts; promote by the outcome rule."""
    cfg = (settings or get_config()).memory.outcome
    for event in events:
        data = event.get("data") or {}
        if event.get("type") != "proposal.status_changed" or data.get("status") not in SEEN:
            continue
        key = data["proposal_id"]
        old = await store.aget(ns(user, PROPOSALS), key)
        statuses = (old.value["statuses"] if old else []) + [data["status"]]
        await store.aput(ns(user, PROPOSALS), key, {
            "job_id": data.get("job_id"), "category": categories.get(data.get("job_id", ""), "unknown"),
            "statuses": statuses, "events": (old.value["events"] if old else []) + [event.get("event_id")]})
    by_category: dict[str, list[dict[str, Any]]] = {}
    for item in await all_items(store, ns(user, PROPOSALS)):
        by_category.setdefault(item.value["category"], []).append(item.value)
    promoted = []
    for category, rows in by_category.items():
        replied = sum(bool(POSITIVE & set(r["statuses"])) for r in rows)
        won = sum("hired" in r["statuses"] for r in rows)
        if await store.aget(ns(user, OUTCOME), category) or not should_promote_outcome(len(rows), replied, cfg):
            continue
        await store.aput(ns(user, OUTCOME), category, {
            "rule": f"{category} jobs get replies ({replied}/{len(rows)} submitted, {won} hired); prefer them.",
            "why": f"at least {cfg.min_submitted} submitted and reply rate >= {cfg.min_reply_rate:.0%}",
            "submitted": len(rows), "replied": replied, "won": won,
            "source_events": [e for r in rows for e in r["events"]], "promoted_at": now()})
        promoted.append(category)
    return promoted


async def list_memory(store: BaseStore, user: str) -> list[dict[str, Any]]:
    return [{"kind": kind, "key": i.key, **i.value} for kind in KINDS for i in await all_items(store, ns(user, kind))]


async def delete_memory(store: BaseStore, user: str, kind: str, key: str) -> bool:
    """Forget a promoted item; its source edits stop counting so it must repeat again."""
    if kind not in KINDS or await store.aget(ns(user, kind), key) is None:
        return False
    await store.adelete(ns(user, kind), key)
    if kind == STYLE:
        for item in await all_items(store, ns(user, EDITS)):
            if key in item.value["patterns"]:
                value = {**item.value, "patterns": [p for p in item.value["patterns"] if p != key]}
                await store.aput(ns(user, EDITS), item.key, value)
    if kind == OUTCOME:
        for item in await all_items(store, ns(user, PROPOSALS)):
            if item.value["category"] == key:
                await store.adelete(ns(user, PROPOSALS), item.key)
    return True
