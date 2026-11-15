"""Bid graph decisions on the dev set: bid F1, scam P/R, injection detection, price in band, cost."""

import argparse
import asyncio
import json
import random
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from agent.config import ROOT, Settings, get_config
from agent.graphs.bid_graph import build_bid_graph, run_job
from agent.local_stack import LocalStack, user_for
from agent.nodes.common import BidContext, NodeCache
from agent.nodes.decide import skip_flags_fired
from evals.metrics import percentile, precision_recall_f1
from evals.runners.rag_eval import commit_hash
from rag.variants.base import Variant

DEV = ROOT / "evals" / "datasets" / "dev" / "labels.jsonl"
JOBS = ROOT / "gigsim" / "seed" / "jobs_dev_pool.jsonl"
RESULTS = ROOT / "evals" / "results"
CHEAP = ["scout", "analyst", "risk_assessor", "fit_matcher", "pricing", "verifier", "compliance"]
SAMPLE = {"scam": 6, "injection": 4, "bid": 10, "skip": 10}
TODAY = "2024-08-01"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def with_cheap_model(settings: Settings, model: str) -> Settings:
    """Same config, cheap nodes on another model."""
    profile = settings.profile
    nodes = {n: profile.node(n).model_copy(update={"model": model}) for n in CHEAP}
    profiles = {**settings.models.profiles,
                settings.models.active_profile: profile.model_copy(update=nodes)}
    return settings.model_copy(update={"models": settings.models.model_copy(update={"profiles": profiles})})


def stratified(labels: list[dict[str, Any]], seed: int, exclude: set[str] | None = None) -> list[dict[str, Any]]:
    """Per persona: scams, injections, then bid and skip jobs, seeded."""
    rng = random.Random(seed)
    labels = [lab for lab in labels if lab["job_id"] not in (exclude or set())]
    picked = []
    for persona in sorted({lab["persona"] for lab in labels}):
        mine = sorted((lab for lab in labels if lab["persona"] == persona), key=lambda x: x["job_id"])
        pools = {"scam": [x for x in mine if x["is_scam"]],
                 "injection": [x for x in mine if x["has_injection"]],
                 "bid": [x for x in mine if x["decision"] == "bid" and not x["is_scam"] and not x["has_injection"]],
                 "skip": [x for x in mine if x["decision"] == "skip" and not x["is_scam"] and not x["has_injection"]]}
        for kind, n in SAMPLE.items():
            picked += rng.sample(pools[kind], min(n, len(pools[kind])))
    return picked


def score(rows: list[dict[str, Any]]) -> dict[str, Any]:
    ran = [r for r in rows if r["predicted"]]
    _, _, f1 = precision_recall_f1([r["predicted"] == "bid" for r in ran], [r["gold"] == "bid" for r in ran])
    sp, sr, _ = precision_recall_f1([r["pred_scam"] for r in ran], [r["is_scam"] for r in ran])
    injected = [r for r in ran if r["has_injection"]]
    clean = [r for r in ran if not r["has_injection"]]
    priced = [r for r in ran if r["gold"] == "bid" and r["price"] is not None and r["band"]]
    latency = [r["latency_s"] for r in ran]
    return {
        "jobs": len(rows), "completed": len(ran),
        "needs_attention": sum(r["status"] == "needs_attention" for r in rows),
        "bid_f1": round(f1, 4),
        "predicted": {k: sum(r["predicted"] == k for r in ran) for k in ("bid", "watch", "skip")},
        "scam_precision": round(sp, 4), "scam_recall": round(sr, 4),
        "injection_detection_rate": round(mean(r["pred_injection"] for r in injected), 4) if injected else None,
        "injection_false_positive_rate": round(mean(r["pred_injection"] for r in clean), 4) if clean else None,
        "price_in_band": round(mean(r["band"][0] <= r["price"] <= r["band"][1] for r in priced), 4) if priced else None,
        "price_in_band_jobs": len(priced),
        "latency_s": {"p50": round(percentile(latency, 50), 2), "p95": round(percentile(latency, 95), 2)},
        "tokens_per_job": round(mean(r["tokens"] for r in ran), 1) if ran else 0,
        "usd_per_job": round(mean(r["usd"] for r in ran), 6) if ran else 0,
    }


async def run(labels: list[dict[str, Any]], settings: Settings, folder: Path,
              retriever: Variant | None = None, cache: NodeCache | None = None) -> list[dict[str, Any]]:
    jobs = {j["job_id"]: j for j in read_jsonl(JOBS)}
    # decisions only: stop before the writer
    stack, graph = LocalStack(folder, retriever=retriever), build_bid_graph(stop_before=["writer"])
    cache = cache or NodeCache(settings.nodes.cache_dir)
    contexts: dict[str, BidContext] = {}
    rows = []
    for i, label in enumerate(labels, start=1):
        persona = label["persona"]
        if persona not in contexts:
            layer = stack.layer(user_for(persona))
            await layer.discover()
            contexts[persona] = BidContext(layer=layer, persona=persona, settings=settings, cache=cache)
        start = time.perf_counter()
        try:
            state = await run_job(jobs[label["job_id"]], contexts[persona], TODAY, graph)
            error = None
        except Exception as err:  # noqa: BLE001
            state, error = {}, f"{type(err).__name__}: {err}"
        decision, risk, quote = state.get("decision"), state.get("risk_report"), state.get("price_quote")
        rows.append({
            "job_id": label["job_id"], "persona": persona, "gold": label["decision"], "is_scam": label["is_scam"],
            "has_injection": label["has_injection"], "band": label["fair_price_band"],
            "predicted": decision.action if decision else None,
            "reasons": decision.reasons if decision else state.get("errors", [error]),
            "status": state.get("status", "error"),
            "pred_scam": bool(risk and skip_flags_fired(risk, settings.decision)),
            "pred_injection": bool(risk and risk.injection_detected),
            "risk_signals": risk.signals if risk else [], "fit": state["fit_report"].score if state.get("fit_report") else None,
            "price": quote.amount if quote else None,
            "tokens": state.get("token_count", 0),
            "usd": round(sum(e["data"].get("usd", 0) for e in state.get("trace", []) if e["kind"] == "llm"), 6),
            "latency_s": round(time.perf_counter() - start, 2), "failed": state.get("failed", []),
            "llm_calls_not_cached": sum(1 for e in state.get("trace", []) if e["kind"] == "llm" and not e["data"].get("cached")),
        })
        print(f"  {i:>3}/{len(labels)} {persona:<12} gold {label['decision']:<4} -> {rows[-1]['predicted']} "
              f"({rows[-1]['latency_s']}s)")
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Decision metrics for the bid graph")
    parser.add_argument("--full", action="store_true", help="all 600 dev jobs")
    parser.add_argument("--cheap-model", default=None, help="override the cheap nodes, e.g. qwen3:8b")
    parser.add_argument("--jobs", default=None, help="comma separated job ids instead of the sample")
    parser.add_argument("--fresh", action="store_true", help="new seed, disjoint from the first sample")
    parser.add_argument("--corroboration", choices=["on", "off"], default=None,
                        help="override decision.model_flags_need_rule")
    args = parser.parse_args()
    settings = get_config()
    if args.corroboration:
        rules = settings.decision.model_copy(update={"model_flags_need_rule": args.corroboration == "on"})
        settings = settings.model_copy(update={"decision": rules})
    if args.cheap_model:
        settings = with_cheap_model(settings, args.cheap_model)
    model = settings.profile.analyst.model
    labels = read_jsonl(DEV)
    if args.jobs:
        wanted = set(args.jobs.split(","))
        labels = [lab for lab in labels if lab["job_id"] in wanted]
    elif args.fresh:
        first = {lab["job_id"] for lab in stratified(labels, settings.data.seed)}
        labels = stratified(labels, settings.data.seed + 1, exclude=first)
    elif not args.full:
        labels = stratified(labels, settings.data.seed)
    with tempfile.TemporaryDirectory() as tmp:
        rows = asyncio.run(run(labels, settings, Path(tmp)))
    name = model.replace(":", "_").replace("/", "_")
    report = {
        "config": {"cheap_nodes": model, "fallback": settings.profile.analyst.fallback.model
                   if settings.profile.analyst.fallback else None,
                   "embedder": settings.rag.embeddings.model, "rag_variant": settings.rag.variant,
                   "thresholds": settings.thresholds.model_dump(), "decision": settings.decision.model_dump()},
        "sample": "full" if args.full else ("jobs" if args.jobs else
                  f"stratified per persona {SAMPLE}" + (", fresh seed, disjoint from the first sample" if args.fresh else "")),
        "commit": commit_hash(), "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "metrics": score(rows),
        "per_persona": {p: score([r for r in rows if r["persona"] == p]) for p in sorted({r["persona"] for r in rows})},
        "rows": rows,
    }
    suffix = "_jobs" if args.jobs else ""
    if args.fresh:
        suffix += "_fresh"
    if args.corroboration:
        suffix += f"_corroboration_{args.corroboration}"
    path = RESULTS / f"decisions_{name}{'_full' if args.full else ''}{suffix}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report["metrics"], indent=1))
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
