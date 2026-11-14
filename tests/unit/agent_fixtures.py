from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from mcp import ClientSession
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from agent.config import McpClientConfig, get_config
from agent.mcp_client import McpLayer
from gigsim.app import create_app
from gigsim.settings import load_settings
from mcp_servers.common import RateLimiter
from mcp_servers.conftest import adapter_for
from mcp_servers.marketplace.server import build_server as marketplace
from mcp_servers.portfolio.server import build_server as portfolio
from mcp_servers.workspace.server import build_server as workspace
from rag.embeddings import FakeEmbedder
from rag.index.store import MemoryStore
from rag.ingest.chunking import FixedChunker
from rag.ingest.indexer import index_documents
from rag.ingest.loaders import PersonaLoader
from rag.variants.v0_naive import V0Naive

_RETRIEVER: V0Naive | None = None


def fake_retriever() -> V0Naive:
    global _RETRIEVER
    if _RETRIEVER is None:
        store, embedder = MemoryStore(), FakeEmbedder(128)
        for persona in ("ai_ml", "fullstack", "data_analyst"):
            index_documents(PersonaLoader(persona).load(), persona, store, embedder, FixedChunker(200, 40))
        _RETRIEVER = V0Naive(store, embedder)
    return _RETRIEVER


def gigsim(tmp: Path) -> FastAPI:
    return create_app(load_settings(overrides={
        "storage": str(tmp / "gigsim.db"), "scenario": "dev",
        "chaos": {"error_rate": 0.0, "latency_ms_max": 0},
        "rate_limit": {"capacity": 10_000, "refill_per_second": 1000},
        "clients": {"mode": "rule_only", "llm": {"cache_dir": str(tmp / "llm")}},
    }))


def servers(tmp: Path, app: FastAPI | None = None, transport: httpx.AsyncBaseTransport | None = None) -> dict[str, FastMCP]:
    limiter = RateLimiter(100_000, 100_000)
    factory = adapter_for(app, transport) if transport else adapter_for(app)
    return {
        "marketplace": marketplace(adapter_factory=factory, limiter=limiter, audit_path=tmp / "marketplace.jsonl"),
        "portfolio": portfolio(retriever=fake_retriever(), limiter=limiter, audit_path=tmp / "portfolio.jsonl"),
        "workspace": workspace(folder=tmp / "ws", limiter=limiter, audit_path=tmp / "workspace.jsonl"),
    }


def client_cfg(**update: Any) -> McpClientConfig:
    cfg = get_config().mcp_client
    base = {"servers": {k: v for k, v in cfg.servers.items() if k != "github"}, "backoff_s": 0.0}
    return cfg.model_copy(update={**base, **update})


def layer_for(found: dict[str, FastMCP], cfg: McpClientConfig | None = None,
              broken: set[str] | None = None) -> McpLayer:
    def session(name: str) -> AbstractAsyncContextManager[ClientSession]:
        if name in (broken or set()):
            raise ConnectionError(f"{name} is down")
        return create_connected_server_and_client_session(found[name]._mcp_server)

    return McpLayer(session_factory=session, cfg=cfg or client_cfg())
