from typing import Protocol

import numpy as np
from pydantic import BaseModel

from rag.ingest.documents import Chunk


class Filters(BaseModel):
    types: list[str] | None = None
    project: str | None = None
    outcomes: list[str] | None = None

    def accepts(self, chunk: Chunk) -> bool:
        if self.types and chunk.type not in self.types:
            return False
        if self.project and chunk.project != self.project:
            return False
        return not (self.outcomes and chunk.outcome not in self.outcomes)


class VectorStore(Protocol):
    def doc_hashes(self, persona: str) -> dict[str, str]: ...
    def upsert(self, chunks: list[Chunk], vectors: np.ndarray) -> None: ...
    def delete(self, persona: str, evidence_ids: list[str]) -> None: ...
    def search(self, vector: np.ndarray, persona: str, k: int,
               filters: Filters | None = None) -> list[tuple[Chunk, float]]: ...
    def chunks(self, persona: str) -> list[Chunk]: ...


class MemoryStore:
    """Exact cosine search in numpy; used by tests and small folders."""

    def __init__(self) -> None:
        self.rows: dict[str, tuple[Chunk, np.ndarray]] = {}

    def doc_hashes(self, persona: str) -> dict[str, str]:
        return {c.evidence_id: c.content_hash for c, _ in self.rows.values() if c.persona == persona}

    def upsert(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        for chunk, vector in zip(chunks, vectors, strict=True):
            self.rows[chunk.chunk_id] = (chunk, vector)

    def delete(self, persona: str, evidence_ids: list[str]) -> None:
        gone = set(evidence_ids)
        self.rows = {k: v for k, v in self.rows.items() if not (v[0].persona == persona and v[0].evidence_id in gone)}

    def search(self, vector: np.ndarray, persona: str, k: int,
               filters: Filters | None = None) -> list[tuple[Chunk, float]]:
        pool = [(c, v) for c, v in self.rows.values() if c.persona == persona and (not filters or filters.accepts(c))]
        if not pool:
            return []
        scores = np.stack([v for _, v in pool]) @ vector
        order = np.argsort(-scores, kind="stable")[:k]
        return [(pool[i][0], float(scores[i])) for i in order]

    def chunks(self, persona: str) -> list[Chunk]:
        return sorted((c for c, _ in self.rows.values() if c.persona == persona), key=lambda c: c.chunk_id)
