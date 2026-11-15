import asyncio
import json
from typing import Any

from agent.config import ROOT
from agent.nodes.analyst import AnalystOut
from agent.nodes.common import BidContext, job_text, structured, untrusted
from evals.runners.rag_eval import JOBS, LABELS, RESULTS, read_jsonl

OUT = RESULTS / "rag_requirements.json"


async def extract(job: dict[str, Any], persona: str) -> dict[str, Any]:
    ctx = BidContext(layer=None, persona=persona)  # type: ignore[arg-type]
    out, events, error = await structured(ctx, "analyst", AnalystOut, job=untrusted(job_text(job)))
    ok = [e["data"] for e in events if e["data"]["ok"]]
    model, cached = (ok[0]["model"], ok[0]["cached"]) if ok else (None, False)
    return {"requirements": out.requirements if out else [], "model": model, "cached": cached, "error": error}


async def main() -> None:
    """Analyst requirements for every dev bid job, cached analyst replies first."""
    jobs = {j["job_id"]: j for j in read_jsonl(JOBS)}
    gold = [lab for lab in read_jsonl(LABELS) if lab["decision"] == "bid" and lab["relevant_evidence_ids"]]
    done = json.loads(OUT.read_text()) if OUT.exists() else {}
    for i, label in enumerate(gold):
        if done.get(label["job_id"], {}).get("requirements"):
            continue
        done[label["job_id"]] = await extract(jobs[label["job_id"]], label["persona"])
        OUT.write_text(json.dumps(done, indent=1))
        print(i, label["job_id"], len(done[label["job_id"]]["requirements"]), flush=True)
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    asyncio.run(main())
