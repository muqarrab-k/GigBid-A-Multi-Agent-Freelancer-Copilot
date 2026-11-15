"""GigBid API: auth, jobs, runs with SSE, approvals, proposals, messages, analytics, settings."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from agent.config import ROOT, get_config
from agent.graphs.checkpoint import open_saver
from agent.local_stack import LocalStack
from agent.mcp_client import McpLayer, open_layer
from agent.memory.store import open_store
from apps.api.auth import ensure_reviewer
from apps.api.core import AppState
from apps.api.routers import approvals, auth, jobs, messages, settings, tracking
from apps.api.scheduler import loop

ROUTERS = [auth.router, jobs.router, approvals.router, tracking.router, messages.router, settings.router]


def layer_factory(mode: str):  # type: ignore[no-untyped-def]
    """remote: the MCP servers over HTTP; local: GigSim and the servers in this process."""
    if mode == "remote":
        return open_layer
    stack = LocalStack(ROOT / "data" / "api" / "stack")

    async def local(user: str) -> McpLayer:
        layer = stack.layer(user)
        await layer.discover()
        return layer

    return local


def create_app(state: AppState | None = None) -> FastAPI:
    """Pass a ready AppState in tests; otherwise Postgres checkpoints and store are opened."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with AsyncExitStack() as stack:
            current = state
            if current is None:
                cfg = get_config()
                saver = await stack.enter_async_context(open_saver(cfg))
                store = await stack.enter_async_context(open_store(cfg))
                current = AppState(settings=cfg, saver=saver, store=store, layer_factory=layer_factory(cfg.api.mcp))
            await ensure_reviewer(current.store, current.settings)
            app.state.gigbid = current
            worker = asyncio.create_task(loop(current)) if current.settings.api.scheduler.enabled else None
            yield
            if worker:
                worker.cancel()
            for task in list(current.tasks):
                task.cancel()

    app = FastAPI(title="GigBid API", version="0.2.0", lifespan=lifespan)
    for router in ROUTERS:
        app.include_router(router)

    @app.get("/health", tags=["status"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "gigbid-api"}

    return app


app = create_app()
