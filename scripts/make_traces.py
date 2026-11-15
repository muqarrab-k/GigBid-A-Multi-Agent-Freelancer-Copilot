"""Run three real cases with LangSmith tracing on and share their root traces.

A skipped scam, an approved proposal and a critic loop, on the active model profile, against an
in-process GigSim. Writes the public links to docs/TRACES.md.
Usage: MODEL_PROFILE=open_hosted LANGSMITH_TRACING=true python -m scripts.make_traces
"""

import asyncio
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import langsmith
from langchain_core.tracers.langchain import wait_for_all_tracers
from langsmith.run_trees import get_cached_client

from agent.config import ROOT, get_config
from agent.graphs.bid_graph import build_bid_graph, pending_approval, resume_job, run_job
from agent.local_stack import LocalStack, user_for
from agent.nodes.common import BidContext, NodeCache
from apps.api.core import traced
from apps.api.tracing import setup_tracing
from evals.runners.decision_eval import JOBS, TODAY, read_jsonl

SCAM = "3875ce618027ec20"
BIDS = ["a95a45269fa17e93", "852020c8a2558233", "27d97376f2ac1781", "43041e09d015bbe3"]
OUT = ROOT / "docs" / "TRACES.md"


def share(client: langsmith.Client, trace_id: str) -> str:
    """Public link to the root run tagged with our trace id."""
    query = f'and(eq(metadata_key, "trace_id"), eq(metadata_value, "{trace_id}"))'
    for _ in range(20):
        runs = list(client.list_runs(project_name="gigbid", filter=query, is_root=True))
        if runs:
            oldest = min(runs, key=lambda r: r.start_time)
            return str(client.share_run(oldest.id))
        time.sleep(3)
    raise RuntimeError(f"no root run for trace {trace_id}")


async def case(ctx: BidContext, graph: Any, job: dict[str, Any], label: str) -> tuple[str, dict[str, Any]]:
    trace_id = uuid.uuid4().hex
    with traced(trace_id, job["job_id"], "make_traces", label):
        state = await run_job(job, ctx, TODAY, graph, thread_id=f"{job['job_id']}:{trace_id[:8]}")
    return trace_id, state


async def main() -> None:
    if not setup_tracing():
        raise SystemExit("set LANGSMITH_TRACING=true and LANGSMITH_API_KEY")
    pool = {j["job_id"]: j for j in read_jsonl(JOBS)}
    folder = Path(tempfile.mkdtemp(prefix="gigbid-traces-"))
    layer = LocalStack(folder).layer(user_for("ai_ml"))
    await layer.discover()
    # fresh cache so every model call is traced
    ctx = BidContext(layer=layer, persona="ai_ml", settings=get_config(), cache=NodeCache(folder / "cache"))
    graph = build_bid_graph()
    rows: list[tuple[str, str, str]] = []

    scam_id, scam = await case(ctx, graph, pool[SCAM], "scam")
    print("scam:", scam.get("status"), scam["decision"].reasons if scam.get("decision") else scam.get("errors"))
    rows.append(("Skipped scam", scam_id, f"decision {scam['decision'].action}: {'; '.join(scam['decision'].reasons)}"))

    approved = loop = None
    for job_id in BIDS:
        trace_id, state = await case(ctx, graph, pool[job_id], "bid")
        critiques = state.get("critiques", [])
        print(job_id, state.get("status"), "critiques", [c.verdict for c in critiques])
        if loop is None and len(critiques) >= 2:
            loop = (trace_id, f"job {job_id}: {len(critiques)} critic passes, verdicts "
                              f"{[c.verdict for c in critiques]}, status {state.get('status')}")
        if approved is None and pending_approval(state):
            approve_id = uuid.uuid4().hex
            with traced(approve_id, state["thread_id"], "make_traces", "approve"):
                done = await resume_job(state["thread_id"], {"action": "approve"}, ctx, graph)
            print("approved:", done.get("status"), done.get("submission"))
            approved = (trace_id, approve_id, f"job {job_id}: drafted, then approved; status {done.get('status')}")
        if approved and loop:
            break
    if approved:
        rows.append(("Approved proposal (draft run)", approved[0], approved[2]))
        rows.append(("Approved proposal (approval resume and submit)", approved[1], approved[2]))
    if loop:
        rows.append(("Critic loop", loop[0], loop[1]))

    # send pending runs first
    wait_for_all_tracers()
    client = get_cached_client()
    client.flush()
    lines = ["# Shared LangSmith traces", "",
             "Real runs on the `open_hosted` profile (open-weight models on Groq) against an in-process GigSim,",
             "made by `python -m scripts.make_traces`. Emails, phone numbers and payment details are masked",
             "before upload (`apps/api/tracing.py`). The trace id is the same one the MCP audit logs carry.", "",
             "| case | trace id | what happened | link |", "|---|---|---|---|"]
    for name, trace_id, note in rows:
        lines.append(f"| {name} | `{trace_id}` | {note} | {share(client, trace_id)} |")
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
