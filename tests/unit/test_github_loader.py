import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.types import CallToolResult, EmbeddedResource, TextContent, TextResourceContents

from agent.config import GithubRepo
from rag.embeddings import FakeEmbedder
from rag.index.store import MemoryStore
from rag.ingest.chunking import FixedChunker
from rag.ingest.github_loader import GitHubMcpLoader
from rag.ingest.indexer import index_new_work

TREE = {
    "": [{"name": "README.md", "path": "README.md", "type": "file"},
         {"name": "src", "path": "src", "type": "dir"},
         {"name": "node_modules", "path": "node_modules", "type": "dir"},
         {"name": "logo.png", "path": "logo.png", "type": "file"}],
    "src": [{"name": "app.py", "path": "src/app.py", "type": "file"},
            {"name": "util.ts", "path": "src/util.ts", "type": "file"}],
}
FILES = {"README.md": "# Demo\nA queue worker built with `Celery` and `Redis`.",
         "src/app.py": "def handler(event):\n    return {'ok': True}\n",
         "src/util.ts": "export const add = (a: number, b: number) => a + b;\n"}


class FakeGithub:
    """Answers get_file_contents like the GitHub MCP server."""

    def __init__(self) -> None:
        self.paths: list[str] = []

    async def call_tool(self, name: str, args: dict[str, Any]) -> CallToolResult:
        assert name == "get_file_contents" and args["owner"] == "me" and args["repo"] == "demo"
        path = args["path"]
        self.paths.append(path)
        if path in TREE:
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(TREE[path]))])
        resource = TextResourceContents(uri=f"repo://me/demo/{path}", mimeType="text/plain", text=FILES[path])
        return CallToolResult(content=[TextContent(type="text", text="successfully downloaded"),
                                       EmbeddedResource(type="resource", resource=resource)])


def loader(fake: FakeGithub) -> GitHubMcpLoader:
    @asynccontextmanager
    async def session() -> AsyncIterator[Any]:
        yield fake

    return GitHubMcpLoader(GithubRepo(owner="me", repo="demo", persona="ai_ml"), session)


async def test_loader_reads_readme_and_code_through_mcp() -> None:
    fake = FakeGithub()
    docs = {d.evidence_id: d for d in await loader(fake).aload()}
    assert set(docs) == {"ai_ml:github:me/demo:README.md", "ai_ml:github:me/demo:src/app.py",
                         "ai_ml:github:me/demo:src/util.ts"}
    readme = docs["ai_ml:github:me/demo:README.md"]
    assert readme.type == "readme" and {"Celery", "Redis"} <= set(readme.skills) and readme.project == "demo"
    assert readme.source_path == "github://me/demo/README.md" and readme.persona == "ai_ml"
    assert docs["ai_ml:github:me/demo:src/util.ts"].skills == ["TypeScript"]
    assert "node_modules" not in fake.paths and "logo.png" not in fake.paths


async def test_github_docs_index_incrementally() -> None:
    store, embedder, chunker = MemoryStore(), FakeEmbedder(32), FixedChunker(50, 10)
    first = index_new_work(await loader(FakeGithub()).aload(), "ai_ml", store, embedder, chunker)
    again = index_new_work(await loader(FakeGithub()).aload(), "ai_ml", store, embedder, chunker)
    assert first.added == 3 and again.unchanged == 3 and again.chunks_embedded == 0
