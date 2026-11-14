from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from mcp.server.auth.middleware.auth_context import auth_context_var
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser
from mcp.server.auth.provider import AccessToken
from mcp.server.fastmcp import FastMCP
from pydantic import AnyUrl
from starlette.testclient import TestClient

from mcp_servers.common import RateLimiter
from mcp_servers.conftest import call, connect
from mcp_servers.portfolio.server import build_server
from rag.embeddings import FakeEmbedder
from rag.index.store import MemoryStore
from rag.ingest.chunking import FixedChunker
from rag.ingest.indexer import index_documents
from rag.ingest.loaders import FolderLoader, PersonaLoader
from rag.variants.v0_naive import V0Naive


@pytest.fixture(scope="module")
def retriever() -> V0Naive:
    """All three personas in memory with the fake embedder."""
    store, embedder = MemoryStore(), FakeEmbedder(128)
    for persona in ("ai_ml", "fullstack", "data_analyst"):
        index_documents(PersonaLoader(persona).load(), persona, store, embedder, FixedChunker(200, 40))
    return V0Naive(store, embedder)


@pytest.fixture
def server(retriever: V0Naive, tmp_path: Path) -> FastMCP:
    return build_server(retriever=retriever, limiter=RateLimiter(10_000, 10_000), audit_path=tmp_path / "p.jsonl")


@contextmanager
def as_user(name: str) -> Iterator[None]:
    """Pretend the HTTP auth middleware accepted this user's token."""
    token = auth_context_var.set(AuthenticatedUser(AccessToken(token="t", client_id=name, scopes=["tools"])))
    try:
        yield
    finally:
        auth_context_var.reset(token)


async def search(session: Any, text: str, **kw: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = (await call(session, "search_evidence", requirement=text, **kw))["items"]
    return items


async def test_search_evidence_returns_metadata(server: FastMCP) -> None:
    async with connect(server) as s:
        items = await search(s, "contract clause search with LangChain and pgvector", k=5)
        assert len(items) == 5
        for item in items:
            assert item["evidence_id"].startswith("ai_ml:") and item["snippet"]
            assert {"type", "source", "date", "outcome", "score"} <= set(item)
        only = await search(s, "LangChain pgvector", k=5, types=["case_study"])
        assert {i["type"] for i in only} == {"case_study"}
        won = await search(s, "chatbot", k=5, outcomes=["won"])
        assert won and {i["outcome"] for i in won} == {"won"}


async def test_case_study_skills_resources_prompts(server: FastMCP) -> None:
    async with connect(server) as s:
        case = (await call(s, "get_case_study", case_id="p05"))["case"]
        assert case["evidence_id"] == "ai_ml:case_study:p05" and case["title"]
        missing = await call(s, "get_case_study", case_id="p99")
        assert missing["error"]["code"] == "not_found"

        skills = (await call(s, "list_skills"))["skills"]
        names = {x["skill"]: x for x in skills}
        assert names["background jobs"]["implied"] and "p01" in names["background jobs"]["projects"]
        assert not names["Python"]["implied"] and names["Python"]["evidence_count"] > 10

        templates = {t.uriTemplate for t in (await s.list_resource_templates()).resourceTemplates}
        assert templates == {"portfolio://case/{case_id}", "portfolio://proposal/{proposal_id}",
                             "portfolio://repo/{name}"}
        assert "portfolio://cv" in {str(r.uri) for r in (await s.list_resources()).resources}
        cv = await s.read_resource(AnyUrl("portfolio://cv"))
        assert "Noor Halden" in cv.contents[0].text  # type: ignore[union-attr]
        repo = await s.read_resource(AnyUrl("portfolio://repo/ticket-router"))
        assert "app/tasks.py" in repo.contents[0].text  # type: ignore[union-attr]
        proposal = await s.read_resource(AnyUrl("portfolio://proposal/001"))
        assert "Outcome:" in proposal.contents[0].text  # type: ignore[union-attr]

        prompts = {p.name for p in (await s.list_prompts()).prompts}
        assert prompts == {"answer_screening_question", "find_proof", "pick_best_projects"}
        got = await s.get_prompt("answer_screening_question", {"question": "How do you test models?"})
        assert "How do you test models?" in got.messages[0].content.text  # type: ignore[union-attr]


async def test_tenant_isolation(server: FastMCP) -> None:
    with as_user("tobias"):
        async with connect(server) as s:
            items = await search(s, "LangChain pgvector contract clause search", k=10)
            assert items and all(i["evidence_id"].startswith("fullstack:") for i in items)
            case = (await call(s, "get_case_study", case_id="ai_ml:case_study:p05"))
            assert case["error"]["code"] == "not_found"
            cv = await s.read_resource(AnyUrl("portfolio://cv"))
            assert "Tobias Reyne" in cv.contents[0].text  # type: ignore[union-attr]
    with as_user("mina"):
        async with connect(server) as s:
            assert all(i["evidence_id"].startswith("data_analyst:") for i in await search(s, "dashboard", k=10))


async def test_folder_mode(tmp_path: Path) -> None:
    folder = tmp_path / "work"
    (folder / "shop").mkdir(parents=True)
    (folder / "shop" / "README.md").write_text("# Shop\nA checkout service with Stripe webhooks.")
    (folder / "notes.md").write_text("# Notes\nI also ran a bakery.")
    store, embedder = MemoryStore(), FakeEmbedder(64)
    index_documents(FolderLoader(folder).load(), "local", store, embedder, FixedChunker(50, 10))
    server = build_server(retriever=V0Naive(store, embedder), folder=folder, limiter=RateLimiter(100, 100),
                          audit_path=tmp_path / "a.jsonl")
    with as_user("tobias"):
        async with connect(server) as s:
            items = await search(s, "stripe checkout webhooks", k=2)
    assert items[0]["evidence_id"] == "local:shop/README.md"


def test_http_requires_bearer_token(server: FastMCP) -> None:
    with TestClient(server.streamable_http_app()) as http:
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        headers = {"Accept": "application/json, text/event-stream", "Host": "localhost"}
        assert http.post("/mcp", json=body, headers=headers).status_code == 401
