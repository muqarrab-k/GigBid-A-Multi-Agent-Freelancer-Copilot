import json
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from agent.config import ROOT
from mcp_servers.portfolio.gigbid_portfolio_mcp.folder import Bm25, load_folder
from mcp_servers.portfolio.gigbid_portfolio_mcp.server import build_server

PERSONA = ROOT / "data" / "personas" / "ai_ml"
PACKAGE_PROMPTS = ROOT / "mcp_servers" / "portfolio" / "gigbid_portfolio_mcp" / "prompts"


def test_persona_folder_uses_manifest_ids() -> None:
    docs = load_folder(PERSONA)
    ids = {d.evidence_id for d in docs}
    assert "ai_ml:case_study:p05" in ids and "ai_ml:review:01" in ids
    assert {d.type for d in docs} >= {"case_study", "readme", "code", "review", "proposal"}


def test_plain_folder_without_manifest(tmp_path: Path) -> None:
    (tmp_path / "case_studies").mkdir()
    (tmp_path / "case_studies" / "shop.md").write_text("# Shop rebuild\n\nMoved a Shopify store to Next.js.")
    (tmp_path / "notes.txt").write_text("Gardening notes.")
    hits = Bm25(load_folder(tmp_path)).search("next.js storefront", 5, {"case_study", "document"})
    assert hits[0].doc.evidence_id == "case_studies/shop.md" and hits[0].doc.type == "case_study"


def test_proposals_excluded_unless_asked() -> None:
    index = Bm25(load_folder(PERSONA))
    assert all(h.doc.type != "proposal" for h in index.search("RAG chatbot over contracts", 10,
                                                              {"case_study", "readme", "review", "code"}))
    assert all(h.doc.type == "proposal" for h in index.search("chatbot", 5, {"proposal"}))


def test_package_prompts_match_agent_prompts() -> None:
    for path in PACKAGE_PROMPTS.glob("*.md"):
        assert path.read_text() == (ROOT / "agent" / "prompts" / path.name).read_text()


@pytest.mark.anyio
async def test_tools_over_mcp() -> None:
    server = build_server(PERSONA)
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        assert tools == {"search_evidence", "get_case_study", "get_evidence", "list_skills"}
        found = await client.call_tool("search_evidence", {"requirement": "contract clause search with citations"})
        first = json.loads(found.content[0].text)
        assert first["evidence_id"] == "ai_ml:case_study:p05" or first["project"] == "p05"
        case = await client.call_tool("get_case_study", {"case_id": "p05"})
        assert "clause" in case.content[0].text.lower()
        prompt = await client.get_prompt("find_proof", {"requirement": "Celery"})
        assert "Celery" in prompt.messages[0].content.text
