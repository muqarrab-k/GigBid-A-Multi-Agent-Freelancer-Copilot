"""README and code from GitHub repos, read through the official GitHub MCP server."""

import asyncio
import json
import logging
import re
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from pathlib import PurePosixPath
from typing import Any

from mcp import ClientSession
from mcp.types import CallToolResult, EmbeddedResource, TextContent, TextResourceContents

from agent.config import GithubRepo, get_config
from rag.ingest.documents import Document
from rag.ingest.loaders import CODE_SUFFIXES, LANGUAGES

log = logging.getLogger(__name__)
SKIP_DIRS = {"node_modules", "dist", "build", ".github", "vendor", "__pycache__", ".venv", "venv"}
SessionFactory = Callable[[], AbstractAsyncContextManager[ClientSession]]


def entries(result: CallToolResult) -> list[dict[str, Any]] | None:
    """Directory listing, or None when the result is a file."""
    for item in result.content:
        if isinstance(item, TextContent):
            try:
                data = json.loads(item.text)
            except ValueError:
                continue
            if isinstance(data, list):
                return [e for e in data if isinstance(e, dict)]
    return None


def file_text(result: CallToolResult) -> str:
    for item in result.content:
        if isinstance(item, EmbeddedResource) and isinstance(item.resource, TextResourceContents):
            return item.resource.text
    texts = [i.text for i in result.content if isinstance(i, TextContent)]
    return texts[-1] if texts else ""


def wanted(path: str) -> bool:
    p = PurePosixPath(path)
    if any(part in SKIP_DIRS or part.startswith(".") for part in p.parts[:-1]):
        return False
    return p.name.lower() == "readme.md" or p.suffix in CODE_SUFFIXES


class GitHubMcpLoader:
    """Walks a repo with get_file_contents; same Document metadata as the other loaders."""

    def __init__(self, repo: GithubRepo, session_factory: SessionFactory, max_files: int = 40, max_depth: int = 3) -> None:
        self.repo, self.session_factory = repo, session_factory
        self.max_files, self.max_depth = max_files, max_depth

    async def get(self, session: ClientSession, path: str) -> CallToolResult:
        args = {"owner": self.repo.owner, "repo": self.repo.repo, "path": path}
        if self.repo.ref:
            args["ref"] = self.repo.ref
        return await session.call_tool("get_file_contents", args)

    async def aload(self) -> list[Document]:
        files: list[str] = []
        async with self.session_factory() as session:
            queue = [("", 0)]
            while queue and len(files) < self.max_files:
                path, depth = queue.pop(0)
                listing = entries(await self.get(session, path)) or []
                for entry in sorted(listing, key=lambda e: (e.get("type") != "file", str(e.get("path")))):
                    full = str(entry.get("path") or entry.get("name"))
                    if entry.get("type") == "dir" and depth < self.max_depth and PurePosixPath(full).name not in SKIP_DIRS:
                        queue.append((full, depth + 1))
                    elif (entry.get("type") == "file" and wanted(full) and entry.get("size", 1) != 0
                          and len(files) < self.max_files):
                        files.append(full)
            docs = []
            for path in files:
                try:
                    text = file_text(await self.get(session, path))
                except Exception as err:  # noqa: BLE001
                    # one bad file never stops the repo
                    log.warning("skipping %s: %s", path, type(err).__name__)
                    continue
                if text.strip():
                    docs.append(self.document(path, text))
        return docs

    def document(self, path: str, text: str) -> Document:
        suffix = PurePosixPath(path).suffix
        readme = PurePosixPath(path).name.lower() == "readme.md"
        skills = [LANGUAGES[suffix]] if suffix in LANGUAGES else []
        skills += re.findall(r"`([A-Za-z][\w.+-]{1,30})`", text)[:5] if readme else []
        name = f"{self.repo.owner}/{self.repo.repo}"
        return Document(
            evidence_id=f"{self.repo.persona}:github:{name}:{path}", persona=self.repo.persona,
            type="readme" if readme else "code", text=text, project=self.repo.repo, skills=sorted(set(skills)),
            source_path=f"github://{name}/{path}", extra={"repo": name, "ref": self.repo.ref},
        )

    def load(self) -> list[Document]:
        return asyncio.run(self.aload())


def configured_repos() -> list[GithubRepo]:
    return get_config().rag.github_repos
