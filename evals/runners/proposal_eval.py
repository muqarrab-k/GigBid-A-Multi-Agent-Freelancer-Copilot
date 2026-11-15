"""Proposals on 15 bid jobs: claims before/after verification, critic loops, compliance, cost, first replies."""

import argparse
import asyncio
import json
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from typing import Any

import httpx

from agent.config import ROOT, get_config
from agent.graphs.bid_graph import build_bid_graph, pending_approval, resume_job, run_job
from agent.local_stack import LocalStack, user_for
from agent.nodes.common import BidContext, NodeCache
from evals.metrics import percentile
from evals.runners.decision_eval import JOBS, RESULTS, TODAY, read_jsonl
from evals.runners.rag_eval import commit_hash

PER_PERSONA = 5
PROPOSAL_NODES = {"writer", "verifier", "critic", "compliance"}
SOURCES = ["decisions_qwen3_4b.json", "decisions_qwen3_4b_fresh_corroboration_off.json"]
TICK_HOURS = 168


def pick_jobs() -> list[tuple[str, str]]:
    """Gold bid jobs the graph also bid on, 5 per persona, from earlier decision runs."""
    rows = [r for name in SOURCES if (RESULTS / name).exists()
            for r in json.loads((RESULTS / name).read_text())["rows"]]
    seen: set[str] = set()
    picked: list[tuple[str, str]] = []
    for r in sorted(rows, key=lambda x: (x["persona"], x["job_id"])):
        if r["gold"] == r["predicted"] == "bid" and r["job_id"] not in seen:
            seen.add(r["job_id"])
            if sum(p == r["persona"] for p, _ in picked) < PER_PERSONA:
                picked.append((r["persona"], r["job_id"]))
    return picked


def eval_auto_approve(payload: dict[str, Any]) -> dict[str, Any]:
    """EVAL HARNESS ONLY: stands in for the human. The app never approves by itself."""
    return {"action": "approve"}


def proposal_cost(state: dict[str, Any]) -> dict[str, Any]:
    llm = [e for e in state.get("trace", []) if e["kind"] == "llm" and e["node"] in PROPOSAL_NODES]
    return {"tokens": sum(e["data"]["input_tokens"] + e["data"]["output_tokens"] for e in llm),
            "usd": round(sum(e["data"]["usd"] for e in llm), 6),
            "writer_models": dict(Counter(e["data"]["model"] for e in llm if e["node"] == "writer" and e["data"]["ok"]))}


async def admin(stack: LocalStack, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    token = stack.gigsim.state.ctx.settings.auth.admin_token
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=stack.gigsim), base_url="http://gigsim") as client:
        res = await client.request(method, f"/admin/{path}", json=body, headers={"Authorization": f"Bearer {token}"})
        res.raise_for_status()
        out: dict[str, Any] = res.json()
        return out


async def run(jobs: list[tuple[str, str]], folder: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    settings = get_config()
    pool = {j["job_id"]: j for j in read_jsonl(JOBS)}
    stack, graph, cache = LocalStack(folder), build_bid_graph(), NodeCache(settings.nodes.cache_dir)
    contexts: dict[str, BidContext] = {}
    rows = []
    for i, (persona, job_id) in enumerate(jobs, start=1):
        if persona not in contexts:
            layer = stack.layer(user_for(persona))
            await layer.discover()
            contexts[persona] = BidContext(layer=layer, persona=persona, settings=settings, cache=cache)
        ctx = contexts[persona]
        start = time.perf_counter()
        try:
            state = await run_job(pool[job_id], ctx, TODAY, graph)
        except Exception as err:  # noqa: BLE001
            state = {"status": "error", "errors": [f"{type(err).__name__}: {err}"[:300]]}
        latency = round(time.perf_counter() - start, 2)
        payload = pending_approval(state)
        report = state.get("verification")
        verdict = state.get("compliance")
        row = {
            "job_id": job_id, "persona": persona, "status_before_approval": state.get("status"),
            "decision": state["decision"].action if state.get("decision") else None,
            "claims_before": report.claims_before if report else None,
            "unsupported_before": report.unsupported_before if report else None,
            "claims_after": report.claims_after if report else None,
            "unsupported_after": report.unsupported_after if report else None,
            "removed_claims": report.removed if report else [],
            "critic_revisions": max(len(state.get("critiques", [])) - 1, 0),
            "critic_unresolved": any(n.startswith("critic_unresolved") for n in state.get("notes", [])),
            "compliance": verdict.verdict if verdict else None,
            "compliance_violations": verdict.violations if verdict else [],
            "words": len(payload["draft"]["cover_letter"].split()) if payload else None,
            "latency_s": latency, **proposal_cost(state), "errors": state.get("errors", []),
            "approval_payload": payload,
        }
        if payload:
            done = await resume_job(job_id, eval_auto_approve(payload), ctx, graph)
            row["status"], row["submission"] = done.get("status"), done.get("submission")
        else:
            row["status"] = state.get("status")
        rows.append(row)
        print(f"  {i:>2}/{len(jobs)} {persona:<12} {job_id} -> {row['status']} "
              f"(unsupported {row['unsupported_before']}->{row['unsupported_after']}, {latency}s)")
    await admin(stack, "POST", "tick", {"hours": TICK_HOURS})
    stats = await admin(stack, "GET", "stats")
    return rows, stats


def summary(rows: list[dict[str, Any]], stats: dict[str, Any]) -> dict[str, Any]:
    drafted = [r for r in rows if r["claims_before"] is not None]
    sent = [r for r in rows if r.get("status") == "submitted"]
    accounts = [a for a in stats["accounts"] if a.get("submitted")]
    replied = sum(a.get("replied", 0) + a.get("interviews", 0) for a in accounts)
    return {
        "jobs": len(rows), "drafted": len(drafted), "submitted": len(sent),
        "blocked_by_compliance": sum(r["status"] == "blocked" for r in rows),
        "unsupported_per_proposal_before": round(mean(r["unsupported_before"] for r in drafted), 2) if drafted else None,
        "unsupported_per_proposal_after": round(mean(r["unsupported_after"] for r in drafted), 2) if drafted else None,
        "claims_per_proposal_before": round(mean(r["claims_before"] for r in drafted), 2) if drafted else None,
        "claims_per_proposal_after": round(mean(r["claims_after"] for r in drafted), 2) if drafted else None,
        "critic_revisions": dict(Counter(r["critic_revisions"] for r in drafted)),
        "critic_unresolved": sum(r["critic_unresolved"] for r in drafted),
        "compliance_violations_caught": sum(len(r["compliance_violations"]) for r in rows),
        "tokens_per_proposal": round(mean(r["tokens"] for r in drafted), 1) if drafted else None,
        "usd_per_proposal": round(mean(r["usd"] for r in drafted), 6) if drafted else None,
        "latency_s": {"p50": round(percentile([r["latency_s"] for r in rows], 50), 2),
                      "p95": round(percentile([r["latency_s"] for r in rows], 95), 2)},
        "first_reply_rate": round(replied / len(sent), 4) if sent else None,
        "gigsim_after_tick": {"hours": TICK_HOURS, "sim_time": stats["sim_time"], "accounts": accounts},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Proposal quality on 15 bid jobs")
    parser.parse_args()
    settings = get_config()
    jobs = pick_jobs()
    with tempfile.TemporaryDirectory() as tmp:
        rows, stats = asyncio.run(run(jobs, Path(tmp)))
    writer = settings.profile.writer
    name = writer.model.replace(":", "_").replace("/", "_")
    report = {
        "config": {"writer": writer.model, "writer_fallback": writer.fallback.model if writer.fallback else None,
                   "verifier": settings.profile.verifier.model, "max_revisions": settings.budgets.max_revisions,
                   "gigsim": "dev scenario, rule_only clients", "approval": "eval harness auto-approve (eval only)"},
        "commit": commit_hash(), "date": datetime.now(UTC).isoformat(timespec="seconds"),
        "metrics": summary(rows, stats), "rows": rows,
    }
    path = RESULTS / f"proposals_{name}.json"
    path.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report["metrics"], indent=1, default=str))
    print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
