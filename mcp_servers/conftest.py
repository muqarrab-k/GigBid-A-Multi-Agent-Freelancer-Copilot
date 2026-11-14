from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from mcp.client.session import ClientSession
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from agent.config import McpUser, get_config
from gigsim.app import create_app
from gigsim.settings import load_settings
from mcp_servers.common import RateLimiter
from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter
from mcp_servers.marketplace.server import build_server

LETTER = (
    "Your churn dashboard needs reliable weekly numbers. I built a retention model in Python with "
    "scikit-learn for a SaaS client that lifted top-decile capture 3.1x and cut manual reporting by 70%. "
    "I would audit the data first, then ship a first version within a week and iterate with you."
)


@pytest.fixture
def gigsim_app(tmp_path: Path) -> FastAPI:
    """GigSim in-process: dev scenario, rule_only clients, no chaos."""
    settings = load_settings(overrides={
        "storage": str(tmp_path / "gigsim.db"),
        "scenario": "dev",
        "chaos": {"error_rate": 0.0, "latency_ms_max": 0},
        "rate_limit": {"capacity": 10_000, "refill_per_second": 1000},
        "clients": {"mode": "rule_only", "llm": {"cache_dir": str(tmp_path / "llm")}},
    })
    return create_app(settings)


def adapter_for(app: FastAPI | None = None,
                transport: httpx.AsyncBaseTransport | None = None) -> Callable[[McpUser], GigSimAdapter]:
    cfg = get_config().marketplace.model_copy(update={"backoff_s": 0.0, "backoff_max_s": 0.0})
    if transport is None:
        assert app is not None
        transport = httpx.ASGITransport(app=app)

    def factory(user: McpUser) -> GigSimAdapter:
        return GigSimAdapter(token=user.gigsim_token, base_url="http://gigsim", transport=transport, settings=cfg)

    return factory


@pytest.fixture
def audit_path(tmp_path: Path) -> Path:
    return tmp_path / "audit" / "marketplace.jsonl"


@pytest.fixture
def market_server(gigsim_app: FastAPI, audit_path: Path) -> FastMCP:
    return build_server(adapter_factory=adapter_for(gigsim_app), limiter=RateLimiter(100_000, 100_000),
                        audit_path=audit_path)


@asynccontextmanager
async def connect(server: FastMCP) -> AsyncIterator[ClientSession]:
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        yield session


async def call(session: ClientSession, tool: str, **args: Any) -> dict[str, Any]:
    result = await session.call_tool(tool, args)
    data: dict[str, Any] = result.structuredContent or {}
    assert data.get("ok") is (not result.isError)
    return data
