"""App state shared by routers: graphs, store, per-user context, thread registry, runs."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from agent.config import ModelSpec, Settings
from agent.graphs.bid_graph import Graph, build_bid_graph, invoke, thread_config
from agent.graphs.conversation_graph import build_conversation_graph
from agent.mcp_client import McpLayer, trace
from agent.memory.store import learn_from_edits, style_rules
from agent.nodes.common import BidContext, Chat, NodeCache
from apps.api.streaming import RunHub, node_event

THREADS, INBOX, PREFS = "threads", "inbox", "prefs"
LayerFactory = Callable[[str], Awaitable[McpLayer]]


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class AppState:
    settings: Settings
    saver: BaseCheckpointSaver[Any]
    store: BaseStore
    layer_factory: LayerFactory
    llm: Callable[[ModelSpec], Chat] | None = None
    cache: NodeCache | None = None
    hub: RunHub = field(default_factory=RunHub)
    layers: dict[str, McpLayer] = field(default_factory=dict)
    tasks: set[asyncio.Task[None]] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.bid_graph: Graph = build_bid_graph(self.saver)
        self.conv_graph: Graph = build_conversation_graph(self.saver)

    def graph(self, kind: str) -> Graph:
        return self.bid_graph if kind == "bid" else self.conv_graph

    async def layer(self, mcp_user: str) -> McpLayer:
        if mcp_user not in self.layers:
            self.layers[mcp_user] = await self.layer_factory(mcp_user)
        return self.layers[mcp_user]

    async def prefs(self, username: str) -> dict[str, Any]:
        item = await self.store.aget((PREFS, username), "settings")
        return item.value if item else {}

    async def user_settings(self, user: dict[str, Any]) -> Settings:
        """Global config with this user's saved overrides."""
        s, p = self.settings, await self.prefs(user["username"])
        update: dict[str, Any] = {}
        if "auto_skip_low_fit" in p:
            update["autonomy"] = s.autonomy.model_copy(update={"auto_skip_low_fit": p["auto_skip_low_fit"]})
        budgets: dict[str, Any] = {k: p[k] for k in ("max_tokens_per_job", "max_revisions") if k in p}
        if budgets:
            update["budgets"] = s.budgets.model_copy(update=budgets)
        if "weekly_connects_budget" in p:
            update["bidding_rules"] = s.bidding_rules.model_copy(
                update={"weekly_connects_budget": p["weekly_connects_budget"]})
        if "saved_searches" in p:
            searches = {**s.scout.saved_searches, user["persona"]: p["saved_searches"]}
            update["scout"] = s.scout.model_copy(update={"saved_searches": searches})
        return s.model_copy(update=update) if update else s

    async def context(self, user: dict[str, Any]) -> BidContext:
        return BidContext(layer=await self.layer(user["mcp_user"]), persona=user["persona"],
                          settings=await self.user_settings(user), cache=self.cache, llm=self.llm,
                          style_rules=await style_rules(self.store, user["username"]))

    # thread registry: the tenant boundary
    async def register(self, username: str, thread_id: str, kind: str, **info: Any) -> dict[str, Any]:
        value = {"thread_id": thread_id, "kind": kind, "created_at": now(), **info}
        await self.store.aput((THREADS, username), thread_id, value)
        return value

    async def thread(self, username: str, thread_id: str) -> dict[str, Any] | None:
        item = await self.store.aget((THREADS, username), thread_id)
        return item.value if item else None

    async def threads(self, username: str, kind: str | None = None) -> list[dict[str, Any]]:
        items = await self.store.asearch((THREADS, username), limit=1000)
        return [i.value for i in items if kind is None or i.value["kind"] == kind]

    def config(self, thread_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": thread_id}, "recursion_limit": self.settings.budgets.max_graph_steps}

    async def snapshot(self, kind: str, thread_id: str) -> Any:
        return await self.graph(kind).aget_state(self.config(thread_id))

    async def pending(self, kind: str, thread_id: str) -> dict[str, Any] | None:
        snap = await self.snapshot(kind, thread_id)
        found = [i.value for task in snap.tasks for i in task.interrupts]
        return found[0] if found else None

    async def run_bid(self, user: dict[str, Any], thread_id: str, payload: dict[str, Any], trace_id: str) -> None:
        """Stream node updates to the hub; failures fall back to the retrying invoke."""
        ctx = await self.context(user)
        graph = self.bid_graph
        with trace(trace_id):
            try:
                async for chunk in graph.astream(payload, thread_config(thread_id, ctx), context=ctx,
                                                 stream_mode="updates"):
                    for node, update in chunk.items():
                        self.hub.publish(thread_id, node_event(node, update))
            except Exception as err:  # noqa: BLE001
                self.hub.publish(thread_id, {"event": "error", "detail": f"{type(err).__name__}: {err}"[:300]})
                await invoke(graph, payload, thread_id, ctx)
        values = (await self.snapshot("bid", thread_id)).values
        self.hub.publish(thread_id, {"event": "done", "status": values.get("status"), "trace_id": trace_id},
                         last=True)

    def spawn(self, coro: Awaitable[None]) -> None:
        task = asyncio.ensure_future(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def learn(self, username: str, values: dict[str, Any]) -> list[str]:
        edits = [e for e in values.get("pending_edits", []) if e.get("kind", "proposal") == "proposal"]
        return await learn_from_edits(self.store, username, edits, self.settings) if edits else []


def new_trace() -> str:
    return uuid.uuid4().hex
