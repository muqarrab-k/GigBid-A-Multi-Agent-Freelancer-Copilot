import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient

from agent.config import get_config
from agent.marketplace_port import NotConfigured, get_marketplace
from mcp_servers.common import RateLimiter
from mcp_servers.conftest import LETTER, adapter_for, call, connect
from mcp_servers.marketplace.server import build_server

TOKEN = {"Authorization": f"Bearer {get_config().mcp.user('noor').token}"}


async def first_job(session: Any) -> dict[str, Any]:
    page = await call(session, "search_jobs", limit=50)
    return next(j for j in page["items"] if not j["untrusted_screening_questions"])


async def draft(session: Any, job: dict[str, Any], key: str, letter: str = LETTER, **kw: Any) -> dict[str, Any]:
    bid = job["budget_max"] or job["hourly_max"] or 40
    return await call(session, "create_proposal_draft", job_id=job["job_id"], cover_letter=letter,
                      bid_amount=bid, idempotency_key=key, **kw)


def audit_lines(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text().splitlines()]


async def test_read_tools_happy_path(market_server: FastMCP) -> None:
    async with connect(market_server) as s:
        page = await call(s, "search_jobs", q="python", limit=5)
        assert page["total"] > 0 and len(page["items"]) == 5
        job = page["items"][0]
        assert job["untrusted_text"]["source"] == "job_post" and "title" not in job
        assert (await call(s, "get_job", job_id=job["job_id"]))["job"]["job_id"] == job["job_id"]
        client = await call(s, "get_client_history", client_id=job["client_id"])
        assert "hire_rate" in client["client"]
        assert (await call(s, "get_connects_balance"))["connects"]["balance"] == 80
        policy = await call(s, "get_policy")
        assert policy["policy"]["version"] == "v1" and policy["capabilities"]["can_submit"]
        assert (await call(s, "list_proposals"))["items"] == []
        assert (await call(s, "list_threads"))["items"] == []
        assert (await call(s, "get_events"))["events"] == []


async def test_same_key_submits_once(market_server: FastMCP) -> None:
    async with connect(market_server) as s:
        job = await first_job(s)
        one = await draft(s, job, "draft-key-1")
        two = await draft(s, job, "draft-key-1")
        assert one["proposal"]["proposal_id"] == two["proposal"]["proposal_id"]
        pid = one["proposal"]["proposal_id"]
        first = await call(s, "submit_proposal", proposal_id=pid, idempotency_key="submit-key-1")
        again = await call(s, "submit_proposal", proposal_id=pid, idempotency_key="submit-key-1")
        assert first["proposal"] == again["proposal"]
        balance = (await call(s, "get_connects_balance"))["connects"]["balance"]
        assert balance == 80 - job["connects_cost"]
        assert len((await call(s, "list_proposals", status="submitted"))["items"]) == 1


async def test_dry_run_changes_nothing(market_server: FastMCP, audit_path: Path) -> None:
    async with connect(market_server) as s:
        job = await first_job(s)
        preview = await draft(s, job, "dry-draft-1", dry_run=True)
        assert preview["dry_run"] and preview["proposal"] is None
        assert preview["connects_cost"] == job["connects_cost"] and preview["policy_check"]["passed"]
        assert (await call(s, "list_proposals"))["items"] == []

        real = await draft(s, job, "real-draft-1")
        pid = real["proposal"]["proposal_id"]
        sub = await call(s, "submit_proposal", proposal_id=pid, idempotency_key="dry-submit-1", dry_run=True)
        assert sub["dry_run"] and sub["blockers"] == []
        assert sub["balance_after"] == 80 - job["connects_cost"]
        assert (await call(s, "get_connects_balance"))["connects"]["balance"] == 80
        assert (await call(s, "list_proposals"))["items"][0]["status"] == "draft"
    dry = [line for line in audit_lines(audit_path) if line["dry_run"]]
    assert {line["tool"] for line in dry} == {"create_proposal_draft", "submit_proposal"}


async def test_policy_violation_names_rule(market_server: FastMCP) -> None:
    async with connect(market_server) as s:
        job = await first_job(s)
        made = await draft(s, job, "bad-draft-1", letter=LETTER + " Email me at noor.h@example.com.")
        assert made["policy_check"] == {"passed": False, "rule_id": "no_email", "detail": "No email addresses."}
        result = await s.call_tool("submit_proposal", {"proposal_id": made["proposal"]["proposal_id"],
                                                       "idempotency_key": "bad-submit-1"})
        assert result.isError
        assert result.structuredContent["error"]["code"] == "policy_violation"  # type: ignore[index]
        assert result.structuredContent["error"]["rule_id"] == "no_email"  # type: ignore[index]


async def test_rate_limit(gigsim_app: FastAPI, audit_path: Path) -> None:
    server = build_server(adapter_factory=adapter_for(gigsim_app), limiter=RateLimiter(1, 2), audit_path=audit_path)
    async with connect(server) as s:
        await call(s, "get_policy")
        await call(s, "get_policy")
        limited = await call(s, "get_policy")
    assert limited["error"]["code"] == "rate_limited" and limited["error"]["retry_after"] > 0


async def test_marketplace_down_is_structured(audit_path: Path) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    server = build_server(adapter_factory=adapter_for(transport=httpx.MockTransport(refuse)),
                          limiter=RateLimiter(1000, 1000), audit_path=audit_path)
    async with connect(server) as s:
        result = await s.call_tool("search_jobs", {})
    assert result.isError
    error = result.structuredContent["error"]  # type: ignore[index]
    assert error["code"] == "marketplace_unavailable" and error["retry_after"] > 0


async def test_retries_reuse_the_same_key() -> None:
    seen: list[str | None] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("Idempotency-Key"))
        if len(seen) < 3:
            return httpx.Response(503, json={"error": "service_unavailable", "detail": "x"}, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"proposal_id": "pr_1", "job_id": "j", "status": "submitted",
                                         "cover_letter": "x", "bid_amount": 10, "connects_spent": 8})

    adapter = adapter_for(transport=httpx.MockTransport(flaky))(get_config().mcp.user("noor"))
    sent = await adapter.submit_proposal("pr_1", "same-key-123")
    assert sent.status == "submitted" and seen == ["same-key-123"] * 3


async def test_audit_only_grows_and_masks_pii(market_server: FastMCP, audit_path: Path) -> None:
    async with connect(market_server) as s:
        await call(s, "get_policy")
        before = audit_path.read_text()
        job = await first_job(s)
        await draft(s, job, "pii-draft-1", dry_run=True,
                    letter=LETTER + " Call +1 555 014 2299 or write to noor.h@example.com, card 4111 1111 1111 1111.")
        await s.call_tool("get_policy", {}, meta={"trace_id": "trace-abc-123"})
    after = audit_path.read_text()
    assert after.startswith(before) and len(after) > len(before)
    lines = audit_lines(audit_path)
    pii = next(x for x in lines if x["tool"] == "create_proposal_draft")
    letter = pii["args"]["cover_letter"]
    assert "[phone]" in letter and "[email]" in letter and "[card]" in letter
    assert "example.com" not in after and "4111" not in after
    assert lines[-1]["trace_id"] == "trace-abc-123"
    assert all({"ts", "user", "tool", "args", "result", "dry_run", "trace_id"} <= set(x) for x in lines)


async def test_client_messages_are_untrusted(market_server: FastMCP, gigsim_app: FastAPI) -> None:
    ctx = gigsim_app.state.ctx
    async with connect(market_server) as s:
        job = await first_job(s)
        made = await draft(s, job, "thread-draft-1")
        await call(s, "submit_proposal", proposal_id=made["proposal"]["proposal_id"], idempotency_key="thread-sub-1")
        row = ctx.store.one("SELECT * FROM proposals LIMIT 1")
        thread_id = ctx.sim.open_thread(row, job["client_id"])
        ctx.sim.post_client_message(thread_id, "question", None, "acct_ai_ml")
        messages = await call(s, "list_messages", thread_id=thread_id)
        msg = messages["items"][0]
        assert msg["sender"] == "client" and msg["text"] is None
        assert msg["untrusted_text"]["source"] == "client_message"
        reply = await call(s, "send_message", thread_id=thread_id, text="Happy to share details on a call.",
                           idempotency_key="reply-key-1", dry_run=True)
        assert reply["dry_run"] and reply["message"] is None
        assert len((await call(s, "list_messages", thread_id=thread_id))["items"]) == 1


def test_http_requires_bearer_token(market_server: FastMCP) -> None:
    with TestClient(market_server.streamable_http_app()) as http:
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        headers = {"Accept": "application/json, text/event-stream", "Host": "localhost"}
        assert http.post("/mcp", json=body, headers=headers).status_code == 401
        bad = http.post("/mcp", json=body, headers={**headers, "Authorization": "Bearer nope"})
        assert bad.status_code == 401
        good = http.post("/mcp", json=body, headers={**headers, **TOKEN})
        assert good.status_code != 401


def test_upwork_mode_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = get_config()
    live = cfg.model_copy(update={"marketplace": cfg.marketplace.model_copy(update={"mode": "upwork"})})
    monkeypatch.setattr("agent.marketplace_port.get_config", lambda: live)
    with pytest.raises(NotConfigured, match="not configured yet"):
        get_marketplace()
