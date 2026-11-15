"""GigBid API: auth, jobs, runs with SSE, approvals, proposals, messages, analytics, settings."""

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agent.config import ROOT, get_config
from agent.graphs.checkpoint import open_saver
from agent.local_stack import LocalStack
from agent.mcp_client import McpLayer, open_layer
from agent.memory.store import open_store
from apps.api.auth import ensure_reviewer
from apps.api.core import AppState
from apps.api.routers import approvals, auth, jobs, messages, portfolio, settings, tracking
from apps.api.scheduler import loop

ROUTERS = [auth.router, jobs.router, approvals.router, tracking.router, messages.router, settings.router,
           portfolio.router]
WEB = ROOT / "apps" / "web" / "dist"


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
            if current is None and fake_mode():
                from apps.api.testmode import build_test_state

                current = build_test_state()
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
    if fake_mode():
        from apps.api.testmode import router as test_router

        app.include_router(test_router)

    @app.get("/health", tags=["status"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "gigbid-api"}

    serve_web(app)
    return app


def fake_mode() -> bool:
    return os.getenv("GIGBID_FAKE_LLM") == "1"


def serve_web(app: FastAPI) -> None:
    """Built web files at /; browser navigations get index.html, API calls get JSON."""
    if not (WEB / "index.html").exists():
        return
    app.mount("/assets", StaticFiles(directory=WEB / "assets"), name="assets")

    @app.middleware("http")
    async def spa(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        page = request.method == "GET" and "text/html" in request.headers.get("accept", "")
        if page and not request.url.path.startswith(("/docs", "/redoc", "/openapi.json", "/assets")):
            path = WEB / request.url.path.lstrip("/")
            page_file = path if path.is_file() and WEB in path.resolve().parents else WEB / "index.html"
            # same url serves json too
            return FileResponse(page_file, headers={"Vary": "Accept", "Cache-Control": "no-store"})
        response = await call_next(request)
        response.headers.setdefault("Vary", "Accept")
        return response


app = create_app()
