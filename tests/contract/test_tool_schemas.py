import json
import os
from pathlib import Path
from typing import Any

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.shared.memory import create_connected_server_and_client_session

from mcp_servers.marketplace.server import build_server as marketplace
from mcp_servers.portfolio.server import build_server as portfolio
from mcp_servers.workspace.server import build_server as workspace

SNAPSHOTS = Path(__file__).with_name("snapshots")
UPDATE = os.getenv("UPDATE_SNAPSHOTS") == "1"


async def tool_contract(server: FastMCP) -> list[dict[str, Any]]:
    """Name, schemas and annotations of every tool."""
    async with create_connected_server_and_client_session(server._mcp_server) as session:
        tools = (await session.list_tools()).tools
    return [
        {
            "name": t.name,
            "input_schema": t.inputSchema,
            "output_schema": t.outputSchema,
            "annotations": t.annotations.model_dump(exclude_none=True) if t.annotations else None,
        }
        for t in sorted(tools, key=lambda t: t.name)
    ]


BUILDERS = {"marketplace": marketplace, "workspace": workspace, "portfolio": portfolio}


@pytest.mark.parametrize("name", sorted(BUILDERS))
async def test_tool_contract_unchanged(name: str, tmp_path: Path) -> None:
    build = BUILDERS[name]
    current = await tool_contract(build(audit_path=tmp_path / "audit.jsonl"))
    path = SNAPSHOTS / f"{name}.json"
    text = json.dumps(current, indent=2, sort_keys=True) + "\n"
    if UPDATE:
        path.write_text(text)
    assert path.exists(), f"missing snapshot, run make snapshot-update ({path})"
    assert path.read_text() == text, f"{name} tool contract changed; if intended run make snapshot-update"
