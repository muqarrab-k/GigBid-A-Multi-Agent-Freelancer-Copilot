import argparse
import json
from typing import Any

from agent.config import ROOT
from evals.runners.rag_eval import RESULTS, run, shared_reranker
from rag.retriever import load_presets, parts_of


def best_preset() -> str:
    """Preset with the highest Recall@5 among saved runs."""
    scores = {}
    for name in load_presets()["presets"]:
        path = RESULTS / f"rag_{name}.json"
        if path.exists():
            scores[name] = json.loads(path.read_text())["overall"]["recall_at_5"]
    return max(scores, key=lambda n: (scores[n], -len(parts_of(n, load_presets()))))


def row(report: dict[str, Any]) -> dict[str, Any]:
    return {"variant": report["variant"], "components": report["components"], **report["overall"],
            "latency_ms": report["latency_ms"], "per_job_type": report["per_job_type"]}


def main() -> None:
    parser = argparse.ArgumentParser(description="Drop one component at a time from the best variant")
    parser.add_argument("--best", default=None)
    args = parser.parse_args()
    best = args.best or best_preset()
    parts = sorted(parts_of(best, load_presets()))
    reranker = shared_reranker()
    full = run(best, reranker=reranker)
    rows = []
    for part in parts:
        rest = "+".join(p for p in parts if p != part) or "v0"
        report = run(rest, reranker=reranker)
        rows.append({"dropped": part, **row(report),
                     "delta_recall_at_5": round(report["overall"]["recall_at_5"] - full["overall"]["recall_at_5"], 4),
                     "delta_mrr": round(report["overall"]["mrr"] - full["overall"]["mrr"], 4),
                     "delta_ndcg_at_10": round(report["overall"]["ndcg_at_10"] - full["overall"]["ndcg_at_10"], 4)})
    out = {"best": row(full), "ablation": rows, "commit": full["commit"], "date": full["date"]}
    path = RESULTS / "rag_ablation.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
