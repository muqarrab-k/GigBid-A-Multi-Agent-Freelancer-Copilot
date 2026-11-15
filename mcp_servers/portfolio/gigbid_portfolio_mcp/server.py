import argparse
import os
import re
from collections import defaultdict
from importlib.resources import files
from pathlib import Path
from string import Template
from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from .folder import Bm25, Doc, load_folder

READ = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
EvidenceType = Literal["case_study", "readme", "code", "review", "proposal", "cv", "document"]
# proof first, phrasing on request
DEFAULT_TYPES = {"case_study", "readme", "code", "review", "cv", "document"}


class EvidenceItem(BaseModel):
    evidence_id: str
    type: str
    source: str
    project: str | None
    date: str | None
    outcome: str | None
    client_industry: str | None
    skills: list[str]
    score: float
    snippet: str


class Evidence(BaseModel):
    evidence_id: str
    type: str
    title: str
    project: str | None
    date: str | None
    skills: list[str]
    source: str
    text: str


class SkillEntry(BaseModel):
    skill: str
    evidence_count: int
    projects: list[str]


def prompt(name: str) -> str:
    return files(__package__ or "gigbid_portfolio_mcp").joinpath(f"prompts/{name}.v1.md").read_text()


def title_of(text: str) -> str:
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    lines = text.strip().splitlines()
    return match.group(1).strip() if match else (lines[0][:120] if lines else "")


def full(doc: Doc) -> Evidence:
    return Evidence(evidence_id=doc.evidence_id, type=doc.type, title=title_of(doc.text), project=doc.project,
                    date=doc.date, skills=doc.skills, source=doc.source, text=doc.text)


def build_server(folder: Path, host: str = "127.0.0.1", port: int = 8103) -> FastMCP:
    """Read-only portfolio server over one folder."""
    docs = load_folder(folder)
    index = Bm25(docs)
    mcp = FastMCP("gigbid-portfolio", instructions="Read-only search over your own portfolio evidence.",
                  host=host, port=port)

    def find(kind: str | None, key: str) -> Doc:
        for doc in docs:
            if (kind is None or doc.type == kind) and key in (doc.evidence_id, doc.project, doc.source):
                return doc
        raise ValueError(f"no {kind or 'evidence'} {key!r} in this portfolio")

    @mcp.tool(annotations=READ)
    def search_evidence(
        requirement: Annotated[str, Field(min_length=3, max_length=2000, description="A job requirement or question")],
        k: Annotated[int, Field(ge=1, le=20)] = 5,
        types: Annotated[list[EvidenceType] | None, Field(max_length=7)] = None,
    ) -> list[EvidenceItem]:
        """Find portfolio evidence for a requirement. Past proposals only when asked for in types."""
        wanted: set[str] = set(types) if types else DEFAULT_TYPES
        return [EvidenceItem(evidence_id=h.doc.evidence_id, type=h.doc.type, source=h.doc.source,
                             project=h.doc.project, date=h.doc.date, outcome=h.doc.outcome,
                             client_industry=h.doc.client_industry, skills=h.doc.skills,
                             score=h.score, snippet=h.snippet) for h in index.search(requirement, k, wanted)]

    @mcp.tool(annotations=READ)
    def get_case_study(case_id: Annotated[str, Field(min_length=1, max_length=200)]) -> Evidence:
        """Full text of one case study, by project id, evidence id or file path."""
        return full(find("case_study", case_id))

    @mcp.tool(annotations=READ)
    def get_evidence(evidence_id: Annotated[str, Field(min_length=1, max_length=300)]) -> Evidence:
        """Full text of any evidence item, by evidence id or file path."""
        return full(find(None, evidence_id))

    @mcp.tool(annotations=READ)
    def list_skills() -> list[SkillEntry]:
        """Skills tagged in the portfolio manifest, with counts and projects."""
        count: dict[str, int] = defaultdict(int)
        projects: dict[str, set[str]] = defaultdict(set)
        for doc in docs:
            if doc.type == "proposal":
                continue
            for skill in doc.skills:
                count[skill] += 1
                if doc.project:
                    projects[skill].add(doc.project)
        entries = [SkillEntry(skill=s, evidence_count=n, projects=sorted(projects[s])) for s, n in count.items()]
        return sorted(entries, key=lambda e: (-e.evidence_count, e.skill.lower()))

    @mcp.resource("portfolio://case/{case_id}", mime_type="text/markdown")
    def case_resource(case_id: str) -> str:
        """A case study in full."""
        return find("case_study", case_id).text

    @mcp.resource("portfolio://proposal/{proposal_id}", mime_type="text/markdown")
    def proposal_resource(proposal_id: str) -> str:
        """A past proposal with its outcome."""
        doc = find("proposal", proposal_id)
        return f"Outcome: {doc.outcome}\n\n{doc.text}"

    @mcp.prompt(name="answer_screening_question", description="Answer a screening question from my portfolio")
    def answer_screening_question(question: str) -> str:
        return Template(prompt("portfolio_screening_answer")).substitute(question=question)

    @mcp.prompt(name="find_proof", description="Find proof for a job requirement")
    def find_proof(requirement: str) -> str:
        return Template(prompt("portfolio_find_proof")).substitute(requirement=requirement)

    @mcp.prompt(name="pick_best_projects", description="Pick my 3 best projects for this job")
    def pick_best_projects(job_post: str) -> str:
        return Template(prompt("portfolio_best_projects")).substitute(job_post=job_post)

    return mcp


def main() -> None:
    parser = argparse.ArgumentParser(description="GigBid portfolio MCP server (read-only, folder mode)")
    parser.add_argument("--dir", default=os.getenv("PORTFOLIO_DIR"), help="portfolio folder (or PORTFOLIO_DIR)")
    parser.add_argument("--http", action="store_true", help="Streamable HTTP instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8103)
    args = parser.parse_args()
    if not args.dir or not Path(args.dir).is_dir():
        parser.error("set PORTFOLIO_DIR or --dir to an existing folder")
    server = build_server(Path(args.dir), args.host, args.port)
    server.run(transport="streamable-http" if args.http else "stdio")


if __name__ == "__main__":
    main()
