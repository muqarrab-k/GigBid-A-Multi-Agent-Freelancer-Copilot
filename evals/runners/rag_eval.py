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
from rag.retriever import build_store, get_retriever, load_presets, parts_of
from rag.variants.base import Variant
from rag.variants.v3_rerank import CrossEncoderReranker

LABELS = ROOT / "evals" / "datasets" / "dev" / "labels.jsonl"
JOBS = ROOT / "gigsim" / "seed" / "jobs_dev_pool.jsonl"
RESULTS = ROOT / "evals" / "results"
REQUIREMENTS = RESULTS / "rag_requirements.json"
K = 10
MANY_REQS = 4
SWEEP = [0.01, 0.02, 0.05, 0.1, 0.2, 0.3]


def read_jsonl(path: Any) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def summarise(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"jobs": 0}
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


def load_jobs() -> dict[str, dict[str, Any]]:
    """Dev jobs with analyst requirements attached where we have them."""
    reqs = json.loads(REQUIREMENTS.read_text()) if REQUIREMENTS.exists() else {}
    jobs = {j["job_id"]: j for j in read_jsonl(JOBS)}
    for job_id, found in reqs.items():
        jobs[job_id] = {**jobs[job_id], "requirements": found["requirements"]}
    return jobs


def layer(retriever: Any, attr: str) -> Any:
    """First wrapped layer that has this attribute."""
    while retriever is not None and not hasattr(retriever, attr):
        retriever = getattr(retriever, "inner", None)
    return retriever


def call(retriever: Variant, job: dict[str, Any], persona: str,
         filters: Filters | None) -> tuple[list[str], str, float, list[float]]:
    """Ranked ids, ok or no_evidence, milliseconds and grades."""
    start = time.perf_counter()
    crag = layer(retriever, "run")
    if crag is None:
        hits, status, grades = retriever.retrieve(job, persona, K, filters), "ok", []
    else:
        types = getattr(retriever, "types", None)
        if types and (filters is None or not filters.types):
            filters = (filters or Filters()).model_copy(update={"types": types})
        state = crag.run(job, persona, K, filters)
        hits, status, grades = state["hits"], state["status"], state.get("grades", [])
    return [h.evidence_id for h in hits], status, (time.perf_counter() - start) * 1000, grades


def refusals(retriever: Variant, jobs: dict[str, Any], labels: list[dict[str, Any]],
             rows: list[dict[str, Any]], filters: Filters | None) -> dict[str, Any]:
    """Refusal rate on skip jobs that hit a persona gap, and on bid jobs."""
    gap = [lab for lab in labels if lab["decision"] == "skip" and not lab["is_scam"] and not lab["has_injection"]
           and any("gap" in r for r in lab["reasons"])]
    gap_grades = [max(call(retriever, jobs[lab["job_id"]], lab["persona"], filters)[3], default=0.0) for lab in gap]
    bid_grades = [max(r["grades"], default=0.0) for r in rows]
    crag = layer(retriever, "run")

    def rates(t: float) -> dict[str, Any]:
        refused, bid_refused = sum(g < t for g in gap_grades), sum(g < t for g in bid_grades)
        return {"pass_score": t, "gap_skip_refused": refused, "gap_skip_refusal_rate": round(refused / len(gap), 4),
                "bid_refused": bid_refused, "bid_refusal_rate": round(bid_refused / len(rows), 4)}

    # exact only up to the configured pass score
    sweep = [rates(t) for t in SWEEP if t <= crag.pass_score]
    return {"gap_skip_jobs": len(gap), "bid_jobs": len(rows), **rates(crag.pass_score), "sweep": sweep}


def evaluate(retriever: Variant, filters: Filters | None = None) -> dict[str, Any]:
    jobs, labels = load_jobs(), read_jsonl(LABELS)
    gold = [lab for lab in labels if lab["decision"] == "bid" and lab["relevant_evidence_ids"]]
    rows, latencies = [], []
    for label in gold:
        job = jobs[label["job_id"]]
        ranked, status, ms, grades = call(retriever, job, label["persona"], filters)
        latencies.append(ms)
        relevant = set(label["relevant_evidence_ids"])
        rows.append({"job_id": label["job_id"], "persona": label["persona"], "ranked": ranked, "status": status, "grades": grades,
                     "requirements": len(job.get("requirements") or []),
                     "recall_at_5": recall_at_k(ranked, relevant, 5), "mrr": mrr(ranked, relevant),
                     "ndcg_at_10": ndcg_at_k(ranked, relevant, 10)})
    personas = sorted({r["persona"] for r in rows})
    report: dict[str, Any] = {
        "overall": summarise(rows),
        "per_persona": {p: summarise([r for r in rows if r["persona"] == p]) for p in personas},
        "per_job_type": {f"{MANY_REQS}+ requirements": summarise([r for r in rows if r["requirements"] >= MANY_REQS]),
                         f"<{MANY_REQS} requirements": summarise([r for r in rows if r["requirements"] < MANY_REQS])},
        "latency_ms": {"p50": round(percentile(latencies, 50), 1), "p95": round(percentile(latencies, 95), 1)},
    }
    if layer(retriever, "run") is not None:
        report["refusal"] = refusals(retriever, jobs, labels, rows, filters)
    report["per_job"] = rows
    return report


def shared_reranker() -> CrossEncoderReranker:
    """One reranker and score cache for every variant in a run."""
    r = load_presets()["rerank"]
    return CrossEncoderReranker([r["model"] or get_config().rag.reranker.model, r["fallback"]], r["max_length"])


def run(name: str, store_backend: str | None = None, types: list[str] | None = None,
        reranker: CrossEncoderReranker | None = None) -> dict[str, Any]:
    filters = Filters(types=types) if types else None
    cfg = get_config().rag
    embedder = get_embedder(cfg.embeddings)
    retriever = get_retriever(name, build_store(cfg, embedder, store_backend), embedder, reranker)
    result = evaluate(retriever, filters)
    reranker = getattr(layer(retriever, "grader"), "grader", None) or getattr(layer(retriever, "reranker"), "reranker", None)
    report = {
        "variant": name,
        "components": sorted(parts_of(name, load_presets())),
        "embedder": embedder.model,
        "reranker": getattr(reranker, "model", None),
        "store": store_backend or cfg.store.backend,
        "chunking": cfg.chunking.model_dump(),
        "k": K,
        "type_filter": filters.types if filters else None,
        "requirements_source": str(REQUIREMENTS.relative_to(ROOT)),
        "commit": commit_hash(),
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset": "dev bid jobs with gold relevant_evidence_ids (evals/datasets/dev/labels.jsonl)",
        **result,
    }
    suffix = f"_only_{'_'.join(filters.types)}" if filters and filters.types else ""
    path = RESULTS / f"rag_{name}{suffix}.json"
    path.write_text(json.dumps(report, indent=2))
    shown = ("variant", "reranker", "overall", "per_job_type", "latency_ms", "refusal")
    print(json.dumps({k: report[k] for k in shown if k in report}, indent=1))
    print(f"wrote {path.relative_to(ROOT)}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Retrieval metrics on dev bid jobs")
    parser.add_argument("--variant", nargs="+", default=[None])
    parser.add_argument("--store", choices=["pgvector", "memory"], default=None)
    parser.add_argument("--types", default=None, help="diagnostic: only these evidence types, comma separated")
    args = parser.parse_args()
    reranker = shared_reranker()
    for name in args.variant:
        run(name or get_config().rag.variant, args.store, args.types.split(",") if args.types else None, reranker)


if __name__ == "__main__":
    main()
