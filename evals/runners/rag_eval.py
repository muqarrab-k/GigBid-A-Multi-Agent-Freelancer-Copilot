import argparse
import json
import subprocess
import time
from datetime import UTC, datetime
from statistics import mean
from typing import Any

from agent.config import ROOT, get_config
from evals.metrics import mrr, ndcg_at_k, percentile, recall_at_k
from rag.embeddings import get_embedder
from rag.index.store import Filters
from rag.retriever import build_store, get_retriever

LABELS = ROOT / "evals" / "datasets" / "dev" / "labels.jsonl"
JOBS = ROOT / "gigsim" / "seed" / "jobs_dev_pool.jsonl"
RESULTS = ROOT / "evals" / "results"
K = 10


def read_jsonl(path: Any) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "jobs": len(rows),
        "recall_at_5": round(mean(r["recall_at_5"] for r in rows), 4),
        "mrr": round(mean(r["mrr"] for r in rows), 4),
        "ndcg_at_10": round(mean(r["ndcg_at_10"] for r in rows), 4),
    }


def commit_hash() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              cwd=ROOT, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieval metrics on dev bid jobs")
    parser.add_argument("--variant", default=None)
    parser.add_argument("--store", choices=["pgvector", "memory"], default=None)
    parser.add_argument("--types", default=None, help="diagnostic: only these evidence types, comma separated")
    args = parser.parse_args()
    filters = Filters(types=args.types.split(",")) if args.types else None
    cfg = get_config().rag
    embedder = get_embedder(cfg.embeddings)
    retriever = get_retriever(args.variant, build_store(cfg, embedder, args.store), embedder)

    jobs = {j["job_id"]: j for j in read_jsonl(JOBS)}
    gold = [lab for lab in read_jsonl(LABELS) if lab["decision"] == "bid" and lab["relevant_evidence_ids"]]
    rows, latencies = [], []
    for label in gold:
        start = time.perf_counter()
        hits = retriever.retrieve(jobs[label["job_id"]], label["persona"], K, filters)
        latencies.append((time.perf_counter() - start) * 1000)
        ranked, relevant = [h.evidence_id for h in hits], set(label["relevant_evidence_ids"])
        rows.append({"job_id": label["job_id"], "persona": label["persona"], "ranked": ranked,
                     "recall_at_5": recall_at_k(ranked, relevant, 5), "mrr": mrr(ranked, relevant),
                     "ndcg_at_10": ndcg_at_k(ranked, relevant, 10)})

    personas = sorted({r["persona"] for r in rows})
    report = {
        "variant": retriever.name,
        "embedder": embedder.model,
        "store": args.store or cfg.store.backend,
        "chunking": cfg.chunking.model_dump(),
        "k": K,
        "type_filter": filters.types if filters else None,
        "commit": commit_hash(),
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset": "dev bid jobs with gold relevant_evidence_ids (evals/datasets/dev/labels.jsonl)",
        "overall": summarise(rows),
        "per_persona": {p: summarise([r for r in rows if r["persona"] == p]) for p in personas},
        "latency_ms": {"p50": round(percentile(latencies, 50), 1), "p95": round(percentile(latencies, 95), 1)},
        "per_job": rows,
    }
    suffix = f"_only_{'_'.join(filters.types)}" if filters and filters.types else ""
    path = RESULTS / f"rag_{retriever.name}{suffix}.json"
    path.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("variant", "embedder", "overall", "per_persona", "latency_ms")}, indent=1))
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
