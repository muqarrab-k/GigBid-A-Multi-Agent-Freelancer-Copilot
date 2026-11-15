"""SSE bridge: node-by-node events from a LangGraph run, replayable by late listeners."""

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any


class RunHub:
    """Events per thread, kept in memory while the process lives."""

    def __init__(self) -> None:
        self.events: dict[str, list[dict[str, Any]]] = {}
        self.done: dict[str, bool] = {}
        self.changed: dict[str, asyncio.Event] = {}

    def start(self, thread_id: str) -> None:
        self.events[thread_id], self.done[thread_id] = [], False
        self.changed[thread_id] = asyncio.Event()

    def publish(self, thread_id: str, event: dict[str, Any], last: bool = False) -> None:
        self.events.setdefault(thread_id, []).append(event)
        self.done[thread_id] = last or self.done.get(thread_id, False)
        flag = self.changed.setdefault(thread_id, asyncio.Event())
        flag.set()

    def running(self, thread_id: str) -> bool:
        return thread_id in self.done and not self.done[thread_id]

    async def follow(self, thread_id: str) -> AsyncIterator[dict[str, Any]]:
        sent = 0
        while True:
            flag = self.changed.setdefault(thread_id, asyncio.Event())
            flag.clear()
            events = self.events.get(thread_id, [])
            for event in events[sent:]:
                yield event
            sent = len(events)
            if self.done.get(thread_id, True):
                return
            await flag.wait()


def sse(event: dict[str, Any]) -> str:
    return f"event: {event.get('event', 'message')}\ndata: {json.dumps(event, default=str)}\n\n"


def node_event(node: str, update: Any) -> dict[str, Any]:
    """Small summary of one node's update; full state stays in the checkpointer."""
    if node == "__interrupt__":
        return {"event": "approval_required", "node": "approval_gate"}
    data = update if isinstance(update, dict) else {}
    out: dict[str, Any] = {"event": "node", "node": node, "keys": sorted(data)}
    if "status" in data:
        out["status"] = data["status"]
    if data.get("errors"):
        out["errors"] = data["errors"]
    return out
