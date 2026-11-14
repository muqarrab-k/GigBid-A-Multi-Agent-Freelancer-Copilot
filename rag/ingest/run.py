import argparse
import json
import time
from collections import Counter
from datetime import UTC, datetime

from agent.config import ROOT, get_config
from rag.embeddings import CachedEmbedder, get_embedder
from rag.ingest.chunking import get_chunker
from rag.ingest.indexer import index_documents
from rag.ingest.loaders import PersonaLoader, persona_names
from rag.retriever import build_store

INDEX_REPORT = ROOT / "evals" / "results" / "rag_index.json"


def main() -> None:
    """Index every persona into the configured store."""
    parser = argparse.ArgumentParser(description="Index persona portfolios")
    parser.add_argument("--store", choices=["pgvector", "memory"], default=None)
    parser.add_argument("--embedder", choices=["default", "fallback", "ollama"], default="default")
    args = parser.parse_args()
    cfg = get_config().rag
    start = time.perf_counter()
    embedder = get_embedder(cfg.embeddings, None if args.embedder == "default" else args.embedder)
    load_seconds = round(time.perf_counter() - start, 1)
    store = build_store(cfg, embedder, args.store)
    chunker = get_chunker(cfg.chunking)

    personas = {}
    for persona in persona_names():
        docs = PersonaLoader(persona).load()
        stats = index_documents(docs, persona, store, embedder, chunker)
        chunks = store.chunks(persona)
        personas[persona] = {**stats.model_dump(), "chunks_total": len(chunks),
                             "chunks_by_type": dict(Counter(c.type for c in chunks))}
        print(f"  {persona:<13} docs {stats.documents}, chunks {len(chunks)}, embedded {stats.chunks_embedded}, "
              f"removed {stats.removed}, {stats.seconds}s")

    cache = embedder.stats if isinstance(embedder, CachedEmbedder) else {}
    report = {
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "embedder": embedder.model,
        "dim": embedder.dim,
        "store": args.store or cfg.store.backend,
        "chunking": cfg.chunking.model_dump(),
        "model_load_seconds": load_seconds,
        "embed_seconds": round(float(cache.get("seconds", 0)), 1),
        "texts_embedded": cache.get("embedded", 0),
        "texts_from_cache": cache.get("cached", 0),
        "total_seconds": round(time.perf_counter() - start, 1),
        "personas": personas,
    }
    INDEX_REPORT.write_text(json.dumps(report, indent=2))
    print(f"  total {report['total_seconds']}s (embedding {report['embed_seconds']}s), wrote {INDEX_REPORT.name}")


if __name__ == "__main__":
    main()
