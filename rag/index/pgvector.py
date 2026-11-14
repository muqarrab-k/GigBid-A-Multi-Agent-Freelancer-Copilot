import re
from typing import Any

import numpy as np
import psycopg
from psycopg.rows import dict_row

from rag.index.store import Filters
from rag.ingest.documents import Chunk

COLUMNS = ["chunk_id", "evidence_id", "chunk_index", "text", "persona", "type", "project", "skills", "date",
           "client_industry", "outcome", "source_path", "content_hash"]


def literal(vector: np.ndarray) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in vector) + "]"


class PgVectorStore:
    """Chunks and embeddings in Postgres, exact cosine search (fine at this size)."""

    def __init__(self, dsn: str, schema: str, model: str, dim: int) -> None:
        self.dsn, self.dim = dsn, dim
        self.table = f"{schema}.chunks_{re.sub(r'[^a-z0-9]+', '_', model.lower()).strip('_')}"
        self.schema = schema
        self.ensure()

    def connect(self) -> psycopg.Connection[dict[str, Any]]:
        return psycopg.connect(self.dsn, row_factory=dict_row)

    def ensure(self) -> None:
        with self.connect() as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            conn.execute(f"CREATE SCHEMA IF NOT EXISTS {self.schema}")
            conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {self.table} (
                    chunk_id TEXT PRIMARY KEY, evidence_id TEXT NOT NULL, chunk_index INT NOT NULL,
                    text TEXT NOT NULL, persona TEXT NOT NULL, type TEXT NOT NULL, project TEXT,
                    skills TEXT[] NOT NULL DEFAULT '{{}}', date TEXT, client_industry TEXT, outcome TEXT,
                    source_path TEXT NOT NULL, content_hash TEXT NOT NULL, embedding vector({self.dim}) NOT NULL)""")
            conn.execute(f"CREATE INDEX IF NOT EXISTS {self.table.split('.')[1]}_persona ON {self.table} (persona, evidence_id)")

    def doc_hashes(self, persona: str) -> dict[str, str]:
        with self.connect() as conn:
            rows = conn.execute(f"SELECT DISTINCT evidence_id, content_hash FROM {self.table} WHERE persona = %s",
                                (persona,)).fetchall()
        return {r["evidence_id"]: r["content_hash"] for r in rows}

    def upsert(self, chunks: list[Chunk], vectors: np.ndarray) -> None:
        cols = ", ".join([*COLUMNS, "embedding"])
        marks = ", ".join(["%s"] * len(COLUMNS) + ["%s::vector"])
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in [*COLUMNS[1:], "embedding"])
        rows = [(*[getattr(c, col) for col in COLUMNS], literal(v)) for c, v in zip(chunks, vectors, strict=True)]
        with self.connect() as conn, conn.cursor() as cur:
            cur.executemany(f"INSERT INTO {self.table} ({cols}) VALUES ({marks}) "
                            f"ON CONFLICT (chunk_id) DO UPDATE SET {updates}", rows)

    def delete(self, persona: str, evidence_ids: list[str]) -> None:
        if evidence_ids:
            with self.connect() as conn:
                conn.execute(f"DELETE FROM {self.table} WHERE persona = %s AND evidence_id = ANY(%s)",
                             (persona, evidence_ids))

    def search(self, vector: np.ndarray, persona: str, k: int,
               filters: Filters | None = None) -> list[tuple[Chunk, float]]:
        where, params = ["persona = %s"], [persona]
        if filters and filters.types:
            where.append("type = ANY(%s)")
            params.append(filters.types)  # type: ignore[arg-type]
        if filters and filters.project:
            where.append("project = %s")
            params.append(filters.project)
        if filters and filters.outcomes:
            where.append("outcome = ANY(%s)")
            params.append(filters.outcomes)  # type: ignore[arg-type]
        vec = literal(vector)
        sql = (f"SELECT {', '.join(COLUMNS)}, 1 - (embedding <=> %s::vector) AS score FROM {self.table} "
               f"WHERE {' AND '.join(where)} ORDER BY embedding <=> %s::vector, chunk_id LIMIT %s")
        with self.connect() as conn:
            rows = conn.execute(sql, (vec, *params, vec, k)).fetchall()
        return [(Chunk(**{c: r[c] for c in COLUMNS}), float(r["score"])) for r in rows]

    def chunks(self, persona: str) -> list[Chunk]:
        with self.connect() as conn:
            rows = conn.execute(f"SELECT {', '.join(COLUMNS)} FROM {self.table} WHERE persona = %s ORDER BY chunk_id",
                                (persona,)).fetchall()
        return [Chunk(**r) for r in rows]
