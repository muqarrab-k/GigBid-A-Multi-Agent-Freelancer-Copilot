"""Portfolio MCP server: read-only evidence search over one freelancer's portfolio."""

import argparse
import os
import re
from collections import defaultdict
from collections.abc import Callable
from pathlib import Path
from string import Template
from typing import Annotated, Literal

import yaml
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult, ToolAnnotations
from pydantic import BaseModel, Field

from agent.config import get_config
from agent.prompts.loader import load_prompt
from mcp_servers.common import (
    AuditLog,
    RateLimiter,
    ToolFailure,
    ToolOut,
    ToolRunner,
    Verifier,
    auth_settings,
    current_user,
)
from rag.embeddings import get_embedder
from rag.index.store import Filters, MemoryStore
from rag.ingest.chunking import get_chunker
from rag.ingest.documents import Document
from rag.ingest.indexer import index_documents
from rag.ingest.loaders import PERSONAS_DIR, FolderLoader, PersonaLoader
from rag.retriever import get_retriever
from rag.variants.base import Variant

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
EvidenceType = Literal["case_study", "readme", "code", "review", "proposal", "cv", "document"]


class EvidenceItem(BaseModel):
    evidence_id: str
    type: str
    source: str
    date: str | None
    outcome: str | None
    score: float
    project: str | None
    client_industry: str | None
    skills: list[str]
    snippet: str


class CaseStudy(BaseModel):
    evidence_id: str
    project: str | None
    title: str
    client_industry: str | None
    date: str | None
    skills: list[str]
    source: str
    text: str


class SkillEntry(BaseModel):
    skill: str
    evidence_count: int
    projects: list[str]
    implied: bool


class SearchOut(ToolOut):
    items: list[EvidenceItem] = []


class CaseOut(ToolOut):
    case: CaseStudy | None = None


class EvidenceOut(ToolOut):
    evidence: CaseStudy | None = None


class SkillsOut(ToolOut):
    skills: list[SkillEntry] = []


def implied_skills(persona: str) -> set[tuple[str, str]]:
    """(project, skill) pairs the fact sheet marks as implied."""
    path = PERSONAS_DIR / persona / "facts.yaml"
    if not path.exists():
        return set()
    facts = yaml.safe_load(path.read_text())
    return {(p["id"], s) for p in facts.get("projects", []) for s in p.get("implied_skills", [])}


def title_of(text: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else text.strip().splitlines()[0][:120]


def build_server(retriever: Variant | None = None, folder: Path | None = None,
                 loader: Callable[[str], list[Document]] | None = None, limiter: RateLimiter | None = None,
                 audit_path: Path | None = None, port: int | None = None) -> FastMCP:
    """Portfolio server; PORTFOLIO_DIR (or folder) indexes any folder instead of the personas."""
    settings = get_config()
    cfg, rag = settings.mcp, settings.rag
    folder = folder or (Path(os.environ["PORTFOLIO_DIR"]) if os.getenv("PORTFOLIO_DIR") else None)
    port = port or cfg.ports.get("portfolio", 8103)
    rl = settings.marketplace.rate_limit
    runner = ToolRunner(cfg, limiter or RateLimiter(rl.requests_per_minute, rl.burst),
                        AuditLog(audit_path or cfg.audit_dir / "portfolio.jsonl"))
    mcp = FastMCP("gigbid-portfolio", instructions="Read-only search over your own portfolio evidence.",
                  token_verifier=Verifier(cfg), auth=auth_settings(cfg, port), port=port)
    load = loader or ((lambda _: FolderLoader(folder).load()) if folder else (lambda p: PersonaLoader(p).load()))
    docs: dict[str, list[Document]] = {}
    state: dict[str, Variant] = {}

    def tenant() -> str:
        return "local" if folder else current_user(cfg).tenant

    def documents(persona: str) -> list[Document]:
        if persona not in docs:
            docs[persona] = load(persona)
        return docs[persona]

    def search_engine() -> Variant:
        if "retriever" not in state:
            if retriever is not None:
                state["retriever"] = retriever
            elif folder:
                # small folders live in memory
                embedder = get_embedder(rag.embeddings)
                store = MemoryStore()
                index_documents(documents("local"), "local", store, embedder, get_chunker(rag.chunking))
                state["retriever"] = get_retriever(store=store, embedder=embedder)
            else:
                state["retriever"] = get_retriever()
        return state["retriever"]

    def find(persona: str, kind: str, key: str) -> Document:
        for doc in documents(persona):
            if doc.type == kind and key in (doc.evidence_id, doc.project, doc.evidence_id.rsplit(":", 1)[-1]):
                return doc
        raise ToolFailure("not_found", f"no {kind} {key!r} in this portfolio")

    @mcp.tool(annotations=READ)
    async def search_evidence(
        ctx: Context,  # type: ignore[type-arg]
        requirement: Annotated[str, Field(min_length=3, max_length=2000, description="A job requirement or question")],
        k: Annotated[int, Field(ge=1, le=20)] = 5,
        types: Annotated[list[EvidenceType] | None, Field(max_length=7)] = None,
        project: Annotated[str | None, Field(max_length=64)] = None,
        outcomes: list[Literal["won", "replied", "ignored"]] | None = None,
    ) -> Annotated[CallToolResult, SearchOut]:
        """Find portfolio evidence for a requirement: type, source, date, outcome and score."""
        filters = Filters(types=types, project=project, outcomes=outcomes)
        args = {"requirement": requirement, "k": k, **filters.model_dump()}

        async def body(_: object) -> SearchOut:
            hits = search_engine().retrieve(requirement, tenant(), k, filters)
            return SearchOut(items=[EvidenceItem(**h.model_dump(exclude={"text", "chunk_id", "source_path"}),
                                                 source=h.source_path, snippet=h.text[:600]) for h in hits])

        return await runner.run(ctx, "search_evidence", args, SearchOut, body)

    @mcp.tool(annotations=READ)
    async def get_case_study(
        ctx: Context,  # type: ignore[type-arg]
        case_id: Annotated[str, Field(min_length=1, max_length=128, description="Project id (p05) or evidence id")],
    ) -> Annotated[CallToolResult, CaseOut]:
        """Full text of one case study."""
        async def body(_: object) -> CaseOut:
            doc = find(tenant(), "case_study", case_id)
            return CaseOut(case=CaseStudy(evidence_id=doc.evidence_id, project=doc.project, title=title_of(doc.text),
                                          client_industry=doc.client_industry, date=doc.date, skills=doc.skills,
                                          source=doc.source_path, text=doc.text))

        return await runner.run(ctx, "get_case_study", {"case_id": case_id}, CaseOut, body)

    @mcp.tool(annotations=READ)
    async def get_evidence(
        ctx: Context,  # type: ignore[type-arg]
        evidence_id: Annotated[str, Field(min_length=3, max_length=200)],
    ) -> Annotated[CallToolResult, EvidenceOut]:
        """Full text of any evidence item in your portfolio, by evidence id."""
        async def body(_: object) -> EvidenceOut:
            doc = next((d for d in documents(tenant()) if d.evidence_id == evidence_id), None)
            if doc is None:
                raise ToolFailure("not_found", f"no evidence {evidence_id!r} in this portfolio")
            return EvidenceOut(evidence=CaseStudy(evidence_id=doc.evidence_id, project=doc.project,
                                                  title=title_of(doc.text), client_industry=doc.client_industry,
                                                  date=doc.date, skills=doc.skills, source=doc.source_path,
                                                  text=doc.text))

        return await runner.run(ctx, "get_evidence", {"evidence_id": evidence_id}, EvidenceOut, body)

    @mcp.tool(annotations=READ)
    async def list_skills(ctx: Context) -> Annotated[CallToolResult, SkillsOut]:  # type: ignore[type-arg]
        """Skills shown in the portfolio, with counts and the projects that show them."""
        async def body(_: object) -> SkillsOut:
            persona = tenant()
            implied = implied_skills(persona)
            count: dict[str, int] = defaultdict(int)
            projects: dict[str, set[str]] = defaultdict(set)
            implied_only: dict[str, bool] = defaultdict(lambda: True)
            for doc in documents(persona):
                if doc.type == "proposal":
                    continue
                for skill in doc.skills:
                    count[skill] += 1
                    if doc.project:
                        projects[skill].add(doc.project)
                        implied_only[skill] &= (doc.project, skill) in implied
            skills = [SkillEntry(skill=s, evidence_count=n, projects=sorted(projects[s]),
                                 implied=bool(projects[s]) and implied_only[s]) for s, n in count.items()]
            skills.sort(key=lambda e: (-e.evidence_count, e.skill.lower()))
            return SkillsOut(skills=skills)

        return await runner.run(ctx, "list_skills", {}, SkillsOut, body)

    @mcp.resource("portfolio://case/{case_id}", mime_type="text/markdown")
    def case_resource(case_id: str) -> str:
        """A case study in full."""
        return find(tenant(), "case_study", case_id).text

    @mcp.resource("portfolio://proposal/{proposal_id}", mime_type="text/markdown")
    def proposal_resource(proposal_id: str) -> str:
        """A past proposal with its outcome."""
        doc = find(tenant(), "proposal", proposal_id)
        return f"# {doc.extra.get('job_title', 'Proposal')}\n\nOutcome: {doc.outcome}\n\n{doc.text}"

    @mcp.resource("portfolio://repo/{name}", mime_type="text/markdown")
    def repo_resource(name: str) -> str:
        """A repo README plus its file list."""
        persona = tenant()
        readme = find(persona, "readme", name)
        files = [d.source_path for d in documents(persona) if d.type == "code" and f"/repos/{name}/" in d.source_path]
        listing = "\n".join(f"- {f.split(f'/repos/{name}/', 1)[1]}" for f in files)
        return f"{readme.text}\n\n## Files\n{listing}"

    @mcp.resource("portfolio://cv", mime_type="text/plain")
    def cv_resource() -> str:
        """The freelancer's CV."""
        cv = [d for d in documents(tenant()) if d.type == "cv"]
        if not cv:
            raise ToolFailure("not_found", "no CV in this portfolio")
        return cv[0].text

    @mcp.prompt(name="answer_screening_question", description="Answer a screening question from my portfolio")
    def answer_screening_question(question: str) -> str:
        return Template(load_prompt("portfolio_screening_answer")).substitute(question=question)

    @mcp.prompt(name="find_proof", description="Find proof for a job requirement")
    def find_proof(requirement: str) -> str:
        return Template(load_prompt("portfolio_find_proof")).substitute(requirement=requirement)

    @mcp.prompt(name="pick_best_projects", description="Pick my 3 best projects for this job")
    def pick_best_projects(job_post: str) -> str:
        return Template(load_prompt("portfolio_best_projects")).substitute(job_post=job_post)

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="GigBid portfolio MCP server (read-only)")
    parser.add_argument("--http", action="store_true", help="Streamable HTTP instead of stdio")
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args()
    build_server(port=args.port).run(transport="streamable-http" if args.http else "stdio")


if __name__ == "__main__":
    main()
