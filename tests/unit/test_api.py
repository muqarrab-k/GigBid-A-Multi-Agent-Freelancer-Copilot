import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from langgraph.store.memory import InMemoryStore

from agent.graphs.checkpoint import memory_saver
from agent.mcp_client import McpLayer
from apps.api.auth import create_user, ensure_reviewer
from apps.api.core import INBOX, AppState
from apps.api.main import create_app
from tests.unit.fake_layer import FakeLayer
from tests.unit.test_bid_graph_approval import bid_job, open_ctx
from tests.unit.test_conversation_graph import LiaisonChat, reply_of

Client = httpx.AsyncClient


async def client_for(state: AppState) -> Client:
    app = create_app(state)
    # no lifespan under ASGITransport: wire the state by hand
    app.state.gigbid = state
    await ensure_reviewer(state.store, state.settings)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://api")


async def login(client: Client, username: str = "reviewer", password: str = "reviewer-dev") -> dict[str, str]:
    res = await client.post("/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
async def bid_api(tmp_path: Path) -> AsyncIterator[tuple[Client, AppState, list[Any], dict[str, Any]]]:
    """Real GigSim + MCP servers in-process, fake LLM, memory saver and store."""
    ctx, _, stack = open_ctx(tmp_path)
    job = await bid_job(ctx)

    async def layers(user: str) -> McpLayer:
        layer = stack.layer(user)
        await layer.discover()
        return layer

    state = AppState(settings=ctx.settings, saver=memory_saver(), store=InMemoryStore(), layer_factory=layers,
                     llm=ctx.llm, cache=ctx.cache)
    await state.store.aput((INBOX, "reviewer"), job["job_id"], job)
    client = await client_for(state)
    submitted: list[Any] = []
    yield client, state, submitted, job
    await client.aclose()


def sse_events(body: str) -> list[dict[str, Any]]:
    return [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]


async def start_and_wait(client: Client, headers: dict[str, str], job_id: str) -> tuple[str, list[dict[str, Any]]]:
    res = await client.post("/runs", json={"job_id": job_id}, headers=headers)
    assert res.status_code == 202, res.text
    thread_id = res.json()["thread_id"]
    stream = await client.get(f"/runs/{thread_id}/events", headers=headers)
    assert stream.headers["content-type"].startswith("text/event-stream")
    return thread_id, sse_events(stream.text)


async def test_auth_required_and_wrong_password(bid_api: Any) -> None:
    client, *_ = bid_api
    assert (await client.get("/jobs")).status_code == 401
    bad = await client.post("/auth/login", json={"username": "reviewer", "password": "not-the-password"})
    assert bad.status_code == 401
    me = await client.get("/auth/me", headers=await login(client))
    assert me.json()["username"] == "reviewer" and me.json()["persona"] == "ai_ml" and me.json()["hourly_floor"]


async def test_run_streams_then_approve_submits_once(bid_api: Any) -> None:
    client, state, _, job = bid_api
    headers = await login(client)
    thread_id, events = await start_and_wait(client, headers, job["job_id"])
    nodes = [e.get("node") for e in events if e["event"] == "node"]
    assert {"intake", "decide", "writer", "verifier", "compliance", "prepare_approval"} <= set(nodes)
    assert events[-2]["event"] == "approval_required" and events[-1]["event"] == "done"
    assert events[-1]["status"] == "awaiting_approval"

    first = (await client.get("/approvals", headers=headers)).json()["items"]
    # a page refresh reads the checkpointer again
    again = (await client.get("/approvals", headers=headers)).json()["items"]
    assert first == again and first[0]["thread_id"] == thread_id and first[0]["kind"] == "bid"
    assert first[0]["payload"]["claims"]

    inbox = (await client.get("/jobs", headers=headers)).json()["items"]
    assert inbox[0]["job_id"] == job["job_id"] and inbox[0]["recommended_action"] == "bid"
    assert inbox[0]["price"] and inbox[0]["connects_cost"] is not None
    detail = (await client.get(f"/jobs/{job['job_id']}", headers=headers)).json()
    assert detail["job_spec"] and detail["evidence_matrix"] and detail["price_rationale"] and detail["decision_reasons"]

    ok = await client.post(f"/approvals/{thread_id}", json={"action": "approve"}, headers=headers)
    assert ok.status_code == 200 and ok.json()["status"] == "submitted"
    twice = await client.post(f"/approvals/{thread_id}", json={"action": "approve"}, headers=headers)
    assert twice.status_code == 409
    proposals = (await client.get("/proposals", headers=headers)).json()["items"]
    assert [p["status"] for p in proposals] == ["submitted"] and proposals[0]["thread_id"] == thread_id
    assert (await client.get("/approvals", headers=headers)).json()["items"] == []
    # starting the same job again does not start a second run
    rerun = await client.post("/runs", json={"job_id": job["job_id"]}, headers=headers)
    assert rerun.json()["started"] is False


async def test_reject_records_reason(bid_api: Any) -> None:
    client, state, _, job = bid_api
    headers = await login(client)
    thread_id, _ = await start_and_wait(client, headers, job["job_id"])
    res = await client.post(f"/approvals/{thread_id}", json={"action": "reject", "reason": "budget too low"},
                            headers=headers)
    assert res.json()["status"] == "rejected" and res.json()["submission"]["reason"] == "budget too low"
    missing = await client.post(f"/approvals/{thread_id}", json={"action": "reject"}, headers=headers)
    assert missing.status_code in (409, 422)
    analytics = (await client.get("/analytics", headers=headers)).json()
    assert ["human: budget too low", 1] in analytics["rejection_reasons"]
    assert (await client.get("/proposals", headers=headers)).json()["items"] == []


async def test_edit_reruns_compliance_and_feeds_memory(bid_api: Any) -> None:
    client, state, _, job = bid_api
    headers = await login(client)
    thread_id, _ = await start_and_wait(client, headers, job["job_id"])
    payload = (await client.get("/approvals", headers=headers)).json()["items"][0]["payload"]
    edited = payload["draft"]["cover_letter"] + "\n\nEmail me at sam@example.com."
    res = (await client.post(f"/approvals/{thread_id}", json={"action": "edit", "edited_text": edited},
                             headers=headers)).json()
    values = (await state.snapshot("bid", thread_id)).values
    assert values["pending_edits"] and values["pending_edits"][0]["after"] == edited
    # the guard ran again on the human's text
    assert res["status"] == "blocked" and any("no_contact_details" in v for v in values["compliance"].violations)
    edits = await state.store.asearch(("memory", "reviewer", "style_edits"))
    assert len(edits) == 1


async def test_tenant_isolation(bid_api: Any) -> None:
    client, state, _, job = bid_api
    reviewer = await login(client)
    thread_id, _ = await start_and_wait(client, reviewer, job["job_id"])
    await create_user(state.store, "mina2", "another-password", "data_analyst")
    other = await login(client, "mina2", "another-password")
    assert (await client.get("/approvals", headers=other)).json()["items"] == []
    assert (await client.get("/jobs", headers=other)).json()["items"] == []
    assert (await client.post(f"/approvals/{thread_id}", json={"action": "approve"}, headers=other)).status_code == 404
    assert (await client.get(f"/runs/{thread_id}", headers=other)).status_code == 404
    assert (await client.get("/proposals", headers=reviewer)).json()["items"] == []


async def test_settings_never_allow_auto_send(bid_api: Any) -> None:
    client, *_ = bid_api
    headers = await login(client)
    res = await client.put("/settings", json={"auto_skip_low_fit": False, "max_revisions": 1}, headers=headers)
    assert res.json()["auto_skip_low_fit"] is False and res.json()["max_revisions"] == 1
    assert res.json()["auto_send"] is False
    bad = await client.put("/settings", json={"auto_send": True}, headers=headers)
    assert bad.status_code == 422


@pytest.fixture
async def fake_api(tmp_path: Path) -> AsyncIterator[tuple[Client, AppState, FakeLayer]]:
    from agent.config import get_config
    from agent.nodes.common import NodeCache

    layer = FakeLayer("Could we do a call on Thursday?")
    prompts: list[str] = []

    async def layers(user: str) -> FakeLayer:
        return layer

    state = AppState(settings=get_config(), saver=memory_saver(), store=InMemoryStore(),
                     layer_factory=layers,  # type: ignore[arg-type]
                     llm=lambda spec: LiaisonChat(reply_of("interview_request", "Happy to talk."), prompts),  # type: ignore[arg-type,return-value]
                     cache=NodeCache(tmp_path / "cache"))
    client = await client_for(state)
    yield client, state, layer
    await client.aclose()


async def test_degraded_status_when_marketplace_down(fake_api: Any) -> None:
    client, _, layer = fake_api
    headers = await login(client)
    assert (await client.get("/status", headers=headers)).json()["degraded"] is False
    layer.down = True
    status = (await client.get("/status", headers=headers)).json()
    assert status == {"marketplace": "down", "servers": status["servers"], "degraded": True}
    assert (await client.get("/messages", headers=headers)).status_code == 503


async def test_message_draft_and_approve(fake_api: Any) -> None:
    client, _, layer = fake_api
    headers = await login(client)
    threads = (await client.get("/messages", headers=headers)).json()["items"]
    assert threads[0]["thread_id"] == "t1"
    draft = (await client.post("/messages/t1/draft", headers=headers)).json()
    assert draft["intent"] == "interview_request" and draft["pending"]["slots"]
    cid = draft["conversation_id"]
    pending = (await client.get("/approvals", headers=headers)).json()["items"]
    assert pending[0]["kind"] == "conversation" and pending[0]["thread_id"] == cid
    sent = (await client.post(f"/approvals/{cid}", json={"action": "approve"}, headers=headers)).json()
    assert sent["status"] == "sent" and len(layer.sent) == 1
    detail = (await client.get("/messages/t1", headers=headers)).json()
    assert detail["messages"][0]["untrusted"] is True and detail["draft_status"] == "sent"


async def test_memory_viewer_lists_and_deletes(fake_api: Any) -> None:
    from tests.unit.test_memory import edit

    client, state, _ = fake_api
    headers = await login(client)
    from agent.memory.store import learn_from_edits

    await learn_from_edits(state.store, "reviewer", [edit(1), edit(2), edit(3)])
    items = (await client.get("/settings/memory", headers=headers)).json()["items"]
    keys = {i["key"] for i in items}
    assert "removed_term:passionate" in keys and all(i["why"] for i in items)
    gone = await client.delete("/settings/memory/style/removed_term:passionate", headers=headers)
    assert gone.status_code == 204
    left = {i["key"] for i in (await client.get("/settings/memory", headers=headers)).json()["items"]}
    assert "removed_term:passionate" not in left
    assert (await client.delete("/settings/memory/style/nope", headers=headers)).status_code == 404
