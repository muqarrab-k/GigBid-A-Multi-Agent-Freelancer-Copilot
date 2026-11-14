import time
from collections.abc import Callable

import numpy as np
from pydantic import BaseModel

from rag.embeddings import Embedder
from rag.index.store import VectorStore
from rag.ingest.chunking import Chunker
from rag.ingest.documents import Document


class IndexStats(BaseModel):
    persona: str
    documents: int = 0
    added: int = 0
    updated: int = 0
    removed: int = 0
    unchanged: int = 0
    chunks_embedded: int = 0
    seconds: float = 0.0


def write(docs: list[Document], persona: str, store: VectorStore, embedder: Embedder,
          chunker: Chunker, stats: IndexStats, known: dict[str, str]) -> None:
    """Chunk, embed and store new or changed documents."""
    changed = [d for d in docs if known.get(d.evidence_id) != d.content_hash]
    stats.added += sum(d.evidence_id not in known for d in changed)
    stats.updated += sum(d.evidence_id in known for d in changed)
    stats.unchanged += len(docs) - len(changed)
    store.delete(persona, [d.evidence_id for d in changed if d.evidence_id in known])
    chunks = [c for d in changed for c in chunker.split(d)]
    if chunks:
        vectors = embedder.embed_documents([c.text for c in chunks])
        store.upsert(chunks, np.asarray(vectors))
    stats.chunks_embedded += len(chunks)


def index_documents(docs: list[Document], persona: str, store: VectorStore, embedder: Embedder,
                    chunker: Chunker, managed: Callable[[str], bool] = lambda _: True) -> IndexStats:
    """Full sync for one persona: re-embed changed docs, drop deleted ones this loader manages."""
    start = time.perf_counter()
    if any(d.persona != persona for d in docs):
        raise ValueError(f"all documents must belong to {persona}")
    stats = IndexStats(persona=persona, documents=len(docs))
    known = store.doc_hashes(persona)
    gone = sorted(e for e in set(known) - {d.evidence_id for d in docs} if managed(e))
    store.delete(persona, gone)
    stats.removed = len(gone)
    write(docs, persona, store, embedder, chunker, stats, known)
    stats.seconds = round(time.perf_counter() - start, 2)
    return stats


def index_new_work(docs: list[Document], persona: str, store: VectorStore, embedder: Embedder,
                   chunker: Chunker) -> IndexStats:
    """Upload path for the API: add or update items, never delete others."""
    start = time.perf_counter()
    stats = IndexStats(persona=persona, documents=len(docs))
    write([d.model_copy(update={"persona": persona}) for d in docs], persona, store, embedder, chunker,
          stats, store.doc_hashes(persona))
    stats.seconds = round(time.perf_counter() - start, 2)
    return stats
