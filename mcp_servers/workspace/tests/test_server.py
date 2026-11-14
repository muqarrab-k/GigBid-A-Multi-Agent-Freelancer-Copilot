import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient

from mcp_servers.common import RateLimiter
from mcp_servers.conftest import call, connect
from mcp_servers.workspace.server import build_server

WEEK = {"start": "2024-08-05T00:00:00+00:00", "end": "2024-08-09T00:00:00+00:00"}


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    return tmp_path / "workspace"


@pytest.fixture
def server(folder: Path, tmp_path: Path) -> FastMCP:
    return build_server(folder=folder, limiter=RateLimiter(10_000, 10_000), audit_path=tmp_path / "ws.jsonl")


async def slots(session: Any, n: int = 3) -> list[dict[str, Any]]:
    out = await call(session, "free_slots", duration_minutes=30, timezone="America/New_York", limit=n, **WEEK)
    found: list[dict[str, Any]] = out["slots"]
    return found


async def test_free_slots_in_working_hours(server: FastMCP) -> None:
    async with connect(server) as s:
        found = await slots(s, 10)
    assert len(found) == 10
    for slot in found:
        start = datetime.fromisoformat(slot["start"])
        assert start.utcoffset() is not None and str(start.utcoffset()) == "-1 day, 20:00:00"
        local_hour = (start.hour + 9) % 24
        assert 9 <= local_hour < 17


async def test_hold_is_idempotent_and_dry_run_writes_nothing(server: FastMCP, folder: Path) -> None:
    async with connect(server) as s:
        slot = (await slots(s))[0]
        preview = await call(s, "create_tentative_hold", slot=slot, title="Interview", idempotency_key="hold-key-1",
                             dry_run=True)
        assert preview["dry_run"] and preview["hold"] is None and not folder.exists()
        one = await call(s, "create_tentative_hold", slot=slot, title="Interview", idempotency_key="hold-key-1")
        two = await call(s, "create_tentative_hold", slot=slot, title="Interview", idempotency_key="hold-key-1")
        assert one == two and one["hold"]["status"] == "tentative"
        clash = await call(s, "create_tentative_hold", slot=slot, title="Other", idempotency_key="hold-key-2")
        assert clash["error"]["code"] == "slot_unavailable"
        assert slot not in await slots(s, 10)
    saved = json.loads(next(folder.glob("*.json")).read_text())
    assert len(saved["holds"]) == 1


async def test_email_draft_never_sends(server: FastMCP, tmp_path: Path) -> None:
    async with connect(server) as s:
        out = await call(s, "create_email_draft", to="client@example.com", subject="Interview",
                         body="Does Tuesday 10:00 work? Call me on +1 555 014 2299.", idempotency_key="mail-key-1")
        assert out["draft"]["status"] == "draft"
        bad = await s.call_tool("create_email_draft", {"to": "not-an-email", "subject": "x", "body": "y",
                                                       "idempotency_key": "mail-key-2"})
        assert bad.isError
    audit = (tmp_path / "ws.jsonl").read_text()
    assert "client@example.com" not in audit and "[email]" in audit and "[phone]" in audit


async def test_bad_inputs_are_clear(server: FastMCP) -> None:
    async with connect(server) as s:
        tz = await call(s, "free_slots", duration_minutes=30, timezone="Mars/Olympus", **WEEK)
        assert tz["error"]["code"] == "invalid_timezone"
        backwards = await call(s, "free_slots", start=WEEK["end"], end=WEEK["start"], duration_minutes=30,
                               timezone="UTC")
        assert backwards["error"]["code"] == "invalid_range"


def test_http_requires_bearer_token(server: FastMCP) -> None:
    with TestClient(server.streamable_http_app()) as http:
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        headers = {"Accept": "application/json, text/event-stream", "Host": "localhost"}
        assert http.post("/mcp", json=body, headers=headers).status_code == 401
