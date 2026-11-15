"""GigSim and our MCP servers in this process, reached through in-memory MCP sessions."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from agent.config import get_config
from agent.mcp_client import McpLayer
from gigsim.app import create_app
from gigsim.settings import load_settings
from mcp_servers.common import RateLimiter, local_user
from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
from mcp_servers.marketplace.server import build_server as marketplace_server
from mcp_servers.portfolio.server import build_server as portfolio_server
from mcp_servers.workspace.server import build_server as workspace_server
from rag.variants.base import Variant


class LocalStack:
    """One GigSim (dev scenario by default) shared by every user's layer."""

    def __init__(self, folder: Path, scenario: str = "dev", retriever: Variant | None = None) -> None:
        self.gigsim = create_app(load_settings(overrides={
            "storage": str(folder / "gigsim.db"), "scenario": scenario,
            "chaos": {"error_rate": 0.0, "latency_ms_max": 0},
            "rate_limit": {"capacity": 100_000, "refill_per_second": 1000},
        }))
        transport = httpx.ASGITransport(app=self.gigsim)
        limiter = RateLimiter(100_000, 100_000)
        self.servers: dict[str, FastMCP] = {
            "marketplace": marketplace_server(
                adapter_factory=lambda u: GigSimAdapter(token=u.gigsim_token, base_url="http://gigsim", transport=transport),
                limiter=limiter, audit_path=folder / "marketplace.jsonl"),
            "portfolio": portfolio_server(retriever=retriever, limiter=limiter, audit_path=folder / "portfolio.jsonl"),
            "workspace": workspace_server(folder=folder / "workspace", limiter=limiter,
                                          audit_path=folder / "workspace.jsonl"),
        }

    @asynccontextmanager
    async def session(self, name: str, user: str | None = None) -> AsyncIterator[ClientSession]:
        # the server task copies this context, so it sees the user
        mark = local_user.set(user)
        try:
            async with create_connected_server_and_client_session(self.servers[name]._mcp_server) as session:
                yield session
        finally:
            local_user.reset(mark)

    def layer(self, user: str | None = None) -> McpLayer:
        cfg = get_config().mcp_client
        cfg = cfg.model_copy(update={"servers": {k: v for k, v in cfg.servers.items() if k in self.servers}})
        return McpLayer(user=user, session_factory=lambda name: self.session(name, user), cfg=cfg)


def user_for(persona: str) -> str:
    """The MCP user whose tenant is this persona."""
    return next(u.user for u in get_config().mcp.users if u.tenant == persona)
