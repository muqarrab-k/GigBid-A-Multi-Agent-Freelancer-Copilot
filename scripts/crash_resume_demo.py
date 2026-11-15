"""Crash and resume: kill the process at the approval wait and right after submit; GigSim must charge once."""

import argparse
import asyncio
import faulthandler
import json
import os
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent.config import ROOT, get_config
from agent.graphs.bid_graph import (
    build_bid_graph,
    pending_approval,
    resume_job,
    run_job,
    thread_config,
)
from agent.graphs.checkpoint import open_saver
from agent.local_stack import LocalStack, user_for
from agent.nodes.common import BidContext, NodeCache
from evals.runners.decision_eval import JOBS, TODAY, read_jsonl

OUT = ROOT / "evals" / "results" / "crash_resume.json"
JOB, PERSONA = "1c0b990bb7dbe947", "ai_ml"


async def context(folder: Path) -> BidContext:
    settings = get_config()
    layer = LocalStack(folder).layer(user_for(PERSONA))
    await layer.discover()
    # load the embedder before the graph runs
    await layer.call("search_evidence", {"requirement": "warm up", "k": 1})
    return BidContext(layer=layer, persona=PERSONA, settings=settings, cache=NodeCache(settings.nodes.cache_dir))


async def market(ctx: BidContext) -> dict[str, Any]:
    balance = (await ctx.layer.call("get_connects_balance", {}))["connects"]["balance"]
    items = (await ctx.layer.call("list_proposals", {}))["items"]
    return {"balance": balance, "proposals": [{k: p[k] for k in ("proposal_id", "status", "connects_spent")}
                                              for p in items if p["job_id"] == JOB]}


async def phase(name: str, folder: Path, thread: str) -> None:
    ctx = await context(folder)
    async with open_saver() as saver:
        graph = build_bid_graph(saver)
        if name == "start":
            before = await market(ctx)
            job = {j["job_id"]: j for j in read_jsonl(JOBS)}[JOB]
            state = await run_job(job, ctx, TODAY, graph, thread_id=thread)
            payload = pending_approval(state)
            (folder / "start.json").write_text(json.dumps({"market": before, "status": state.get("status"),
                                                           "interrupted": payload is not None}, default=str))
            # waiting for the human; the parent kills us here
            await asyncio.sleep(3600)
        elif name == "approve":
            real = ctx.layer.call

            async def crash_after_submit(tool: str, args: dict[str, Any], forced: Any = None) -> dict[str, Any]:
                out = await real(tool, args, forced)
                if tool == "submit_proposal" and not args.get("dry_run"):
                    # submitted, but we die before the checkpoint
                    os._exit(137)
                return out

            ctx.layer.call = crash_after_submit  # type: ignore[method-assign,assignment]
            await resume_job(thread, {"action": "approve"}, ctx, graph)
        else:
            snapshot = await graph.aget_state(thread_config(thread, ctx))
            pending = list(snapshot.next)
            # the approval is already stored; just continue from the checkpoint
            state = await graph.ainvoke(None, config=thread_config(thread, ctx), context=ctx)
            (folder / "finish.json").write_text(json.dumps({
                "next_before_restart": pending, "status": state.get("status"),
                "submission": state.get("submission"), "market": await market(ctx)}, default=str))


def run(args: list[str], kill_when: Path | None = None) -> int:
    env = {**os.environ, "HF_HUB_OFFLINE": "1"}
    proc = subprocess.Popen([sys.executable, "-m", "scripts.crash_resume_demo", *args], cwd=ROOT, env=env)
    if kill_when:
        while not kill_when.exists() and proc.poll() is None:
            time.sleep(1)
        if proc.poll() is None:
            os.kill(proc.pid, signal.SIGKILL)
    return proc.wait()


def main() -> None:
    parser = argparse.ArgumentParser(description="Crash/resume evidence for the bid graph")
    parser.add_argument("--phase", choices=["start", "approve", "finish"])
    parser.add_argument("--folder", type=Path)
    parser.add_argument("--thread")
    args = parser.parse_args()
    if args.phase:
        # kill -USR1 <pid> prints every stack
        faulthandler.register(signal.SIGUSR1)
        asyncio.run(phase(args.phase, args.folder, args.thread))
        return
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    folder, thread = ROOT / "data" / "cache" / "crash_demo" / stamp, f"crash-{JOB}-{stamp}"
    folder.mkdir(parents=True)
    common = ["--folder", str(folder), "--thread", thread]
    codes = {"start (killed at approval)": run(["--phase", "start", *common], kill_when=folder / "start.json"),
             "approve (dies right after submit)": run(["--phase", "approve", *common]),
             "finish (restart)": run(["--phase", "finish", *common])}
    start = json.loads((folder / "start.json").read_text())
    finish = json.loads((folder / "finish.json").read_text()) if (folder / "finish.json").exists() else {}
    after = finish.get("market", {})
    submitted = [p for p in after.get("proposals", []) if p["status"] == "submitted"]
    audit = [json.loads(x) for x in (folder / "marketplace.jsonl").read_text().splitlines() if x.strip()]
    calls = [a for a in audit if a.get("tool") == "submit_proposal" and not a.get("args", {}).get("dry_run")]
    report = {
        "date": datetime.now(UTC).isoformat(timespec="seconds"), "thread_id": thread, "job_id": JOB,
        "checkpointer": f"postgres schema {get_config().checkpointer.schema_name}",
        "exit_codes": codes, "interrupted_before_kill": start["interrupted"],
        "next_node_after_crash": finish.get("next_before_restart"), "final_status": finish.get("status"),
        "submit_calls_reaching_server": len(calls), "submitted_proposals": len(submitted),
        "connects_before": start["market"]["balance"], "connects_after": after.get("balance"),
        "connects_charged": start["market"]["balance"] - after["balance"] if after else None,
        "connects_cost_of_job": submitted[0]["connects_spent"] if submitted else None,
        "exactly_one_submission": len(submitted) == 1,
        "charged_once": bool(submitted) and start["market"]["balance"] - after["balance"] == submitted[0]["connects_spent"],
    }
    OUT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
