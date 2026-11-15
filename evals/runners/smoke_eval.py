"""Keyless smoke eval for CI: retrieval and decisions on 30 dev jobs, gated by config thresholds."""

import argparse
import asyncio
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from agent.config import ROOT, Settings, get_config
from agent.nodes.common import NodeCache
from evals.metrics import mrr, ndcg_at_k, recall_at_k
from evals.runners import decision_eval, rag_eval
from rag.embeddings import get_embedder
from rag.index.store import MemoryStore
from rag.ingest.chunking import get_chunker
from rag.ingest.indexer import index_documents
from rag.ingest.loaders import PersonaLoader
from rag.retriever import get_retriever
from rag.variants.base import Variant

PERSONAS = ("ai_ml", "data_analyst", "fullstack")
CACHE_DIR = ROOT / "evals" / "cache"
JOB_LIST = CACHE_DIR / "smoke_jobs.json"
RESULT = ROOT / "evals" / "results" / "smoke_eval.json"
PROPOSALS = ROOT / "evals" / "results" / "proposals_openai_gpt-oss-120b.json"
# per persona, from the decision sample
MIX = {"scam": 2, "injection": 2, "bid": 3, "skip": 3}
NO_MODEL = "http://127.0.0.1:9/v1"


class RecordingCache(NodeCache):
    """Node cache that remembers which keys were read."""

    def __init__(self, folder: Path) -> None:
        super().__init__(folder)
        self.used: set[str] = set()

    def get(self, key: str) -> dict[str, Any] | None:
        hit = super().get(key)
        if hit is not None:
            self.used.add(key)
        return hit


def cpu_retriever() -> Variant:
    """Shipped variant over an in-memory index, CPU embedder (no torch, no keys)."""
    cfg = get_config().rag
    embedder = get_embedder(cfg.embeddings, provider="lite")
    store = MemoryStore()
    for persona in PERSONAS:
        index_documents(PersonaLoader(persona).load(), persona, store, embedder, get_chunker(cfg.chunking))
    return get_retriever(None, store, embedder)


def retrieval(retriever: Variant, per_persona: int) -> dict[str, Any]:
    jobs, labels = rag_eval.load_jobs(), rag_eval.read_jsonl(rag_eval.LABELS)
    gold = sorted((x for x in labels if x["decision"] == "bid" and x["relevant_evidence_ids"]), key=lambda x: x["job_id"])
    picked = [x for p in PERSONAS for x in [g for g in gold if g["persona"] == p][:per_persona]]
    rows = []
    for label in picked:
        ranked = rag_eval.call(retriever, jobs[label["job_id"]], label["persona"], None)[0]
        relevant = set(label["relevant_evidence_ids"])
        rows.append({"job_id": label["job_id"], "recall_at_5": recall_at_k(ranked, relevant, 5),
                     "mrr": mrr(ranked, relevant), "ndcg_at_10": ndcg_at_k(ranked, relevant, 10)})
    return {"jobs": len(rows), **{m: round(mean(r[m] for r in rows), 4) for m in ("recall_at_5", "mrr", "ndcg_at_10")}}


def pick(sample: list[dict[str, Any]], replayable: set[str]) -> list[dict[str, Any]]:
    """Per persona: the first scam, injection, bid and skip jobs whose replies fully replay."""
    picked = []
    for persona in PERSONAS:
        mine = [x for x in sample if x["persona"] == persona and x["job_id"] in replayable]
        pools = {"scam": [x for x in mine if x["is_scam"]], "injection": [x for x in mine if x["has_injection"]],
                 "bid": [x for x in mine if x["decision"] == "bid" and not x["is_scam"] and not x["has_injection"]],
                 "skip": [x for x in mine if x["decision"] == "skip" and not x["is_scam"] and not x["has_injection"]]}
        picked += [x for kind, n in MIX.items() for x in pools[kind][:n]]
    return picked


def keyless(settings: Settings) -> Settings:
    """Cheap nodes and fallbacks point at a closed port: only cached replies can succeed."""
    profile = settings.profile
    nodes = {}
    for name in decision_eval.CHEAP:
        spec = profile.node(name)
        fallback = spec.fallback.model_copy(update={"base_url": NO_MODEL}) if spec.fallback else None
        nodes[name] = spec.model_copy(update={"base_url": NO_MODEL, "fallback": fallback})
    profiles = {**settings.models.profiles, settings.models.active_profile: profile.model_copy(update=nodes)}
    return settings.model_copy(update={"models": settings.models.model_copy(update={"profiles": profiles})})


def decisions(retriever: Variant, cache: NodeCache, settings: Settings, record: bool) -> dict[str, Any]:
    """Record: try the whole first decision sample, keep 30 that replay. CI: the saved 30."""
    sample = decision_eval.stratified(decision_eval.read_jsonl(decision_eval.DEV), settings.data.seed)
    if record:
        labels = sample
    else:
        wanted = json.loads(JOB_LIST.read_text())
        labels = [x for x in sample if x["job_id"] in wanted]
    with tempfile.TemporaryDirectory() as tmp:
        rows = asyncio.run(decision_eval.run(labels, keyless(settings), Path(tmp), retriever, cache))
    if record:
        chosen = {x["job_id"] for x in pick(sample, {r["job_id"] for r in rows if not r["failed"]})}
        rows = [r for r in rows if r["job_id"] in chosen]
        JOB_LIST.write_text(json.dumps(sorted(chosen), indent=1))
    metrics = decision_eval.score(rows)
    # replays of replies that were never cached
    metrics["llm_calls_not_cached"] = sum(r["llm_calls_not_cached"] for r in rows)
    metrics["failed_handoffs"] = sum(len(r["failed"]) for r in rows)
    return metrics


def export_cache(cache: RecordingCache, target: Path) -> None:
    """Copy only the replies the smoke run read, for CI."""
    target.mkdir(parents=True, exist_ok=True)
    out = NodeCache(target)
    for key in sorted(cache.used):
        reply = cache.get(key)
        assert reply is not None
        out.put(key, reply)
    out.db.execute("VACUUM")


def committed_claims() -> float:
    """Unsupported claims per proposal after verification, from the committed proposal eval."""
    return float(json.loads(PROPOSALS.read_text())["metrics"]["unsupported_per_proposal_after"])


def check(report: dict[str, Any], settings: Settings) -> list[str]:
    gate = settings.eval
    problems = []
    if report["retrieval"]["recall_at_5"] < gate.min_recall_at_5:
        problems.append(f"Recall@5 {report['retrieval']['recall_at_5']} < {gate.min_recall_at_5}")
    if report["decisions"]["bid_f1"] < gate.min_bid_f1:
        problems.append(f"bid F1 {report['decisions']['bid_f1']} < {gate.min_bid_f1}")
    if report["unsupported_per_proposal"] > gate.max_unsupported_per_proposal:
        problems.append(f"unsupported claims {report['unsupported_per_proposal']} > {gate.max_unsupported_per_proposal}")
    if report["decisions"]["failed_handoffs"]:
        problems.append(f"{report['decisions']['failed_handoffs']} hand-offs failed: replies missing from the cache")
    if report["decisions"]["completed"] < report["decisions"]["jobs"]:
        problems.append("not every smoke job completed")
    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description="Keyless smoke eval")
    parser.add_argument("--record", action="store_true", help="read the full local node cache and export the subset")
    args = parser.parse_args()
    settings = get_config()
    per_persona = settings.eval.smoke_jobs // len(PERSONAS)
    retriever = cpu_retriever()
    cache = RecordingCache(settings.nodes.cache_dir if args.record else CACHE_DIR)
    report: dict[str, Any] = {
        "commit": rag_eval.commit_hash(),
        "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "setup": {"embedder": "lite (fastembed BAAI/bge-small-en-v1.5, CPU)", "store": "memory",
                  "rag_variant": settings.rag.variant, "cheap_nodes": settings.profile.analyst.model,
                  "llm": "replayed from evals/cache/llm.sqlite; no network",
                  "unsupported_claims_source": str(PROPOSALS.relative_to(ROOT))},
        "retrieval": retrieval(retriever, per_persona),
        "decisions": decisions(retriever, cache, settings, args.record),
        "unsupported_per_proposal": committed_claims(),
        "thresholds": settings.eval.model_dump(),
    }
    if args.record:
        export_cache(cache, CACHE_DIR)
    report["failures"] = check(report, settings)
    RESULT.write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("retrieval", "unsupported_per_proposal", "failures")}, indent=1))
    print(json.dumps({k: report["decisions"][k] for k in ("jobs", "completed", "bid_f1", "scam_precision",
                                                           "scam_recall", "failed_handoffs")}))
    print(f"wrote {RESULT.relative_to(ROOT)}")
    if report["failures"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
