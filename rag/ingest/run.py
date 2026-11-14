import argparse
import json
import time
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from agent.config import ROOT, get_config
from agent.mcp_client import McpLayer
from rag.embeddings import CachedEmbedder, get_embedder
from rag.ingest.chunking import get_chunker
from rag.ingest.github_loader import GitHubMcpLoader, configured_repos
from rag.ingest.indexer import index_documents, index_new_work
from rag.ingest.loaders import PersonaLoader, persona_names
from rag.retriever import build_store

INDEX_REPORT = ROOT / "evals" / "results" / "rag_index.json"
GITHUB_REPORT = ROOT / "evals" / "results" / "rag_github_index.json"


def index_github(store: Any, embedder: Any, chunker: Any) -> None:
    """Repos from rag.github_repos, read through the GitHub MCP server."""
    layer = McpLayer()
    if "github" not in layer.servers:
        raise SystemExit("github server not configured: set GITHUB_TOKEN")
    report = []
    for repo in configured_repos():
        docs = GitHubMcpLoader(repo, lambda: layer.client.session("github")).load()
        prefix = f"{repo.persona}:github:{repo.owner}/{repo.repo}:"
        gone = sorted(e for e in store.doc_hashes(repo.persona) if e.startswith(prefix)
                      and e not in {d.evidence_id for d in docs})
        store.delete(repo.persona, gone)
        stats = index_new_work(docs, repo.persona, store, embedder, chunker)
        chunks = [c for c in store.chunks(repo.persona) if c.evidence_id.startswith(prefix)]
        report.append({"repo": f"{repo.owner}/{repo.repo}", "persona": repo.persona, "files": len(docs),
                       "chunks": len(chunks), "removed": len(gone), **stats.model_dump()})
        print(f"  {repo.owner}/{repo.repo}: {len(docs)} files, {len(chunks)} chunks, removed {len(gone)}")
    GITHUB_REPORT.write_text(json.dumps({"date": datetime.now(UTC).isoformat(timespec="seconds"),
                                         "embedder": embedder.model, "repos": report}, indent=2))


def main() -> None:
    """Index every persona into the configured store."""
    parser = argparse.ArgumentParser(description="Index persona portfolios")
    parser.add_argument("--store", choices=["pgvector", "memory"], default=None)
    parser.add_argument("--embedder", choices=["default", "fallback", "ollama"], default="default")
    parser.add_argument("--github", action="store_true", help="only the repos in rag.github_repos")
    args = parser.parse_args()
    cfg = get_config().rag
    start = time.perf_counter()
    embedder = get_embedder(cfg.embeddings, None if args.embedder == "default" else args.embedder)
    load_seconds = round(time.perf_counter() - start, 1)
    store = build_store(cfg, embedder, args.store)
    chunker = get_chunker(cfg.chunking)
    if args.github:
        index_github(store, embedder, chunker)
        return

    personas = {}
    for persona in persona_names():
        docs = PersonaLoader(persona).load()
        # github items are synced by --github
        stats = index_documents(docs, persona, store, embedder, chunker, managed=lambda e: ":github:" not in e)
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
