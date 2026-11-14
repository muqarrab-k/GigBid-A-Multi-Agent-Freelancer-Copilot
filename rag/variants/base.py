from collections.abc import Mapping
from typing import Any, Protocol

from pydantic import BaseModel, Field

from rag.index.store import Filters
from rag.ingest.documents import Chunk

Job = str | Mapping[str, Any]


class EvidenceHit(BaseModel):
    """One evidence item with its best-matching chunk."""

    evidence_id: str
    score: float
    text: str
    chunk_id: str
    type: str
    project: str | None = None
    skills: list[str] = Field(default_factory=list)
    date: str | None = None
    client_industry: str | None = None
    outcome: str | None = None
    source_path: str


class Variant(Protocol):
    name: str

    def retrieve(self, job: Job, persona: str, k: int, filters: Filters | None = None) -> list[EvidenceHit]: ...


def query_text(job: Job) -> str:
    """A job post dict or a plain requirement string."""
    if isinstance(job, str):
        return job
    skills = ", ".join(str(s) for s in job.get("skills") or [])
    parts = [str(job.get("title") or ""), str(job.get("description") or ""), f"Skills: {skills}" if skills else ""]
    return "\n".join(p for p in parts if p).strip()


def best_per_evidence(scored: list[tuple[Chunk, float]], k: int) -> list[EvidenceHit]:
    """Keep the top chunk per evidence item."""
    best: dict[str, tuple[Chunk, float]] = {}
    for chunk, score in scored:
        if chunk.evidence_id not in best or score > best[chunk.evidence_id][1]:
            best[chunk.evidence_id] = (chunk, score)
    ranked = sorted(best.values(), key=lambda x: (-x[1], x[0].evidence_id))[:k]
    return [EvidenceHit(**c.model_dump(include=set(EvidenceHit.model_fields)), score=round(s, 4))
            for c, s in ranked]
