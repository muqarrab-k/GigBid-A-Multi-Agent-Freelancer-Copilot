"""MCP client layer: one connection setup, per-agent tool allowlists, trace ids, degraded mode."""

import asyncio
import contextvars
import json
import logging
import os
import random
import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractAsyncContextManager, contextmanager
from typing import Any, Literal

from langchain_core.tools import BaseTool, StructuredTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp import ClientSession
from mcp.types import CallToolResult, Tool
from pydantic import BaseModel

from agent.config import McpClientConfig, get_config

log = logging.getLogger(__name__)
trace_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("trace_id", default=None)
SessionFactory = Callable[[str], AbstractAsyncContextManager[ClientSession]]
CORE_SERVERS = ("marketplace", "portfolio", "workspace")


class UnknownToolError(RuntimeError):
    """An allowlist names a tool no server offers."""


class MarketplaceDown(BaseModel):
    """Typed result the graph and UI can show and queue on."""

    ok: Literal[False] = False
    error: Literal["marketplace_down"] = "marketplace_down"
    server: str
    detail: str
    retry_after: float = 30


@contextmanager
def trace(trace_id: str | None = None) -> Iterator[str]:
    """Run tool calls under one trace id."""
    value = trace_id or uuid.uuid4().hex
    token = trace_var.set(value)
    try:
        yield value
    finally:
        trace_var.reset(token)


def connections(cfg: McpClientConfig, user: str) -> dict[str, Any]:
    """MultiServerMCPClient connection dicts from config and env."""
    token = get_config().mcp.user(user).token
    out: dict[str, Any] = {}
    for name, conn in cfg.servers.items():
        if conn.transport == "streamable_http":
            out[name] = {"transport": "streamable_http", "url": conn.url,
                         "headers": {"Authorization": f"Bearer {token}"}}
            continue
        secret = os.getenv(conn.token_env) if conn.token_env else None
        if conn.token_env and not secret:
            if conn.optional:
                log.info("skipping %s: %s not set", name, conn.token_env)
                continue
            raise RuntimeError(f"{name} needs {conn.token_env}")
        env = {**conn.env, **({conn.token_as or conn.token_env: secret} if secret and conn.token_env else {})}
        out[name] = {"transport": "stdio", "command": conn.command, "args": conn.args,
                     "env": {"PATH": os.environ.get("PATH", ""), **env}}
    return out


def delimit(value: Any) -> Any:
    """Wrap untrusted_text so the model sees clear data boundaries."""
    if isinstance(value, dict):
        out = {k: delimit(v) for k, v in value.items()}
        text = value.get("untrusted_text")
        if isinstance(text, dict) and "text" in text:
            source = text.get("source", "client")
            out["untrusted_text"] = f"<untrusted source=\"{source}\">\n{text['text']}\n</untrusted>"
        return out
    if isinstance(value, list):
        return [delimit(v) for v in value]
    return value


def is_down(server: str, result: CallToolResult) -> bool:
    error = (result.structuredContent or {}).get("error") if result.isError else None
    return server == "marketplace" and isinstance(error, dict) and error.get("code") == "marketplace_unavailable"


class McpLayer:
    """Discovers tools once, then hands each agent only its allowlisted ones."""

    def __init__(self, user: str | None = None, session_factory: SessionFactory | None = None,
                 cfg: McpClientConfig | None = None) -> None:
        self.cfg = cfg or get_config().mcp_client
        self.user = user or self.cfg.user
        self.conns = connections(self.cfg, self.user)
        self.client = MultiServerMCPClient(self.conns)
        self.session_factory: SessionFactory = session_factory or self.client.session
        self.tools: dict[str, tuple[str, Tool]] = {}

    @property
    def servers(self) -> list[str]:
        return list(self.conns)

    async def discover(self, servers: list[str] | None = None) -> None:
        """List tools on every reachable server, then check allowlists."""
        for server in servers or self.servers:
            try:
                async with self.session_factory(server) as session:
                    listed = await asyncio.wait_for(session.list_tools(), self.cfg.timeout_s)
            except Exception as err:  # noqa: BLE001
                log.warning("cannot list tools on %s: %s", server, err)
                continue
            for tool in listed.tools:
                self.tools[tool.name] = (server, tool)
        self.check_allowlists()

    def check_allowlists(self) -> None:
        """Fail loudly when an allowlist names a tool no server offers."""
        reached = {server for server, _ in self.tools.values()}
        down = [s for s in CORE_SERVERS if s not in reached]
        if down:
            log.warning("cannot check allowlists, servers down: %s", down)
            return
        unknown = {agent: [n for n in names if n not in self.tools]
                   for agent, names in self.cfg.allowlists.items()}
        unknown = {agent: names for agent, names in unknown.items() if names}
        if unknown:
            raise UnknownToolError(f"allowlists name tools no server offers: {unknown}; offered: {sorted(self.tools)}")

    async def server_status(self) -> dict[str, str]:
        """up or down per server."""
        status = {}
        for server in self.servers:
            try:
                async with self.session_factory(server) as session:
                    await asyncio.wait_for(session.list_tools(), self.cfg.timeout_s)
                status[server] = "up"
            except Exception:  # noqa: BLE001
                status[server] = "down"
        return status

    async def call(self, name: str, args: dict[str, Any], forced: dict[str, Any] | None = None) -> dict[str, Any]:
        """Call one tool with trace id, timeout, retries and degraded mode."""
        server, _ = self.tools[name]
        args = {**self.cfg.defaults.get(name, {}), **{k: v for k, v in args.items() if v is not None},
                **(forced or {})}
        meta = {"trace_id": trace_var.get() or uuid.uuid4().hex}
        detail = ""
        for attempt in range(self.cfg.max_retries + 1):
            try:
                async with self.session_factory(server) as session:
                    result = await asyncio.wait_for(session.call_tool(name, args, meta=meta), self.cfg.timeout_s)
                if is_down(server, result):
                    detail = str((result.structuredContent or {}).get("error"))
                else:
                    return result.structuredContent or {"ok": not result.isError,
                                                        "text": " ".join(getattr(c, "text", "") for c in result.content)}
            except Exception as err:  # noqa: BLE001
                detail = f"{type(err).__name__}: {err}"
            if attempt < self.cfg.max_retries:
                await asyncio.sleep(self.cfg.backoff_s * 2**attempt * random.uniform(0.5, 1.0))
        if server == "marketplace":
            return MarketplaceDown(server=server, detail=detail).model_dump()
        return {"ok": False, "error": f"{server}_unavailable", "detail": detail}

    def langchain_tool(self, name: str, forced: dict[str, Any] | None = None) -> BaseTool:
        _, tool = self.tools[name]

        async def run(**kwargs: Any) -> str:
            return json.dumps(delimit(await self.call(name, kwargs, forced)), default=str)

        schema = dict(tool.inputSchema)
        for key, value in self.cfg.defaults.get(name, {}).items():
            # show the agent-facing default
            schema.setdefault("properties", {}).setdefault(key, {})["default"] = value
        return StructuredTool.from_function(coroutine=run, name=name, description=tool.description or name,
                                            args_schema=schema)

    def get_tools(self, agent: str) -> list[BaseTool]:
        """Only the tools on this agent's allowlist."""
        if agent not in self.cfg.allowlists:
            raise UnknownToolError(f"no allowlist for agent {agent!r}")
        names = self.cfg.allowlists[agent]
        missing = [n for n in names if n not in self.tools]
        if missing:
            raise UnknownToolError(f"{agent}: tools not discovered (server down?): {missing}")
        forced = self.cfg.forced_args.get(agent, {})
        return [self.langchain_tool(n, forced.get(n)) for n in names]


async def open_layer(user: str | None = None, servers: list[str] | None = None) -> McpLayer:
    """Layer with tools discovered and allowlists checked."""
    layer = McpLayer(user)
    await layer.discover(servers)
    return layer
