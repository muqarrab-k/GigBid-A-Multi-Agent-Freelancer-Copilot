import json
from pathlib import Path

import httpx
import pytest

from agent.config import get_config
from agent.mcp_client import McpLayer, UnknownToolError, trace
from tests.unit.agent_fixtures import client_cfg, gigsim, layer_for, servers


@pytest.fixture
def layer(tmp_path: Path) -> McpLayer:
    return layer_for(servers(tmp_path, gigsim(tmp_path)))


async def test_each_agent_gets_only_its_allowlist(layer: McpLayer) -> None:
    await layer.discover()
    for agent, names in get_config().mcp_client.allowlists.items():
        assert [t.name for t in layer.get_tools(agent)] == names
    assert layer.get_tools("analyst") == [] and layer.get_tools("compliance") == []
    writer = {t.name for t in layer.get_tools("writer")}
    assert writer == {"search_evidence", "get_case_study", "list_skills", "get_evidence"}
    single = {t.name for t in layer.get_tools("single_react")}
    assert not single & {"submit_proposal", "send_message"}
    assert {"free_slots", "send_message"} <= {t.name for t in layer.get_tools("client_liaison")}
    with pytest.raises(UnknownToolError):
        layer.get_tools("nobody")


async def test_unknown_tool_name_fails_at_startup(tmp_path: Path) -> None:
    allow = {**get_config().mcp_client.allowlists, "scout": ["search_jobs", "teleport"]}
    layer = layer_for(servers(tmp_path, gigsim(tmp_path)), client_cfg(allowlists=allow))
    with pytest.raises(UnknownToolError, match="teleport"):
        await layer.discover()


async def test_trace_id_reaches_audit_log(layer: McpLayer, tmp_path: Path) -> None:
    await layer.discover()
    with trace("trace-xyz-123"):
        out = await layer.call("search_jobs", {"q": "python", "limit": 2})
    assert out["ok"] and len(out["items"]) == 2
    last = json.loads((tmp_path / "marketplace.jsonl").read_text().splitlines()[-1])
    assert last["tool"] == "search_jobs" and last["trace_id"] == "trace-xyz-123"


async def test_tool_output_marks_untrusted_text(layer: McpLayer) -> None:
    await layer.discover()
    tool = next(t for t in layer.get_tools("scout") if t.name == "search_jobs")
    text = await tool.ainvoke({"q": "python", "limit": 1})
    assert '<untrusted source=\\"job_post\\">' in text


async def test_search_evidence_defaults_to_portfolio_types(layer: McpLayer) -> None:
    await layer.discover()
    default = await layer.call("search_evidence", {"requirement": "chatbot with OpenAI", "k": 10})
    assert default["items"] and {i["type"] for i in default["items"]} <= {"case_study", "readme", "code", "review", "cv"}
    explicit = await layer.call("search_evidence", {"requirement": "chatbot with OpenAI", "k": 5, "types": ["proposal"]})
    assert {i["type"] for i in explicit["items"]} == {"proposal"}


async def test_marketplace_down_is_typed(tmp_path: Path) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    gigsim_down = layer_for(servers(tmp_path, transport=httpx.MockTransport(refuse)))
    await gigsim_down.discover()
    out = await gigsim_down.call("get_job", {"job_id": "x"})
    assert out["error"] == "marketplace_down" and out["retry_after"] > 0

    server_down = layer_for(servers(tmp_path, gigsim(tmp_path)), broken={"marketplace"})
    await server_down.discover()
    status = await server_down.server_status()
    assert status == {"marketplace": "down", "portfolio": "up", "workspace": "up"}
    assert server_down.get_tools("writer")
    with pytest.raises(UnknownToolError, match="server down"):
        server_down.get_tools("scout")
