"""Scout: run saved searches, drop jobs already seen (by id or content), return new ones."""

import argparse
import asyncio
import hashlib
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from agent.config import get_config
from agent.nodes.common import BidContext, ToolBox


def content_hash(job: dict[str, Any]) -> str:
    text = f"{job.get('title', '')} {job.get('description') or ''}".lower()
    return hashlib.sha256(" ".join(re.findall(r"[a-z0-9]+", text)).encode()).hexdigest()


class SeenStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.execute("CREATE TABLE IF NOT EXISTS seen (persona TEXT, job_id TEXT, hash TEXT, "
                        "PRIMARY KEY (persona, job_id))")

    def is_new(self, persona: str, job_id: str, digest: str) -> bool:
        row = self.db.execute("SELECT 1 FROM seen WHERE persona = ? AND (job_id = ? OR hash = ?)",
                              (persona, job_id, digest)).fetchone()
        return row is None

    def add(self, persona: str, job_id: str, digest: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO seen VALUES (?, ?, ?)", (persona, job_id, digest))
        self.db.commit()


async def scout(ctx: BidContext, seen: SeenStore) -> list[dict[str, Any]]:
    """New jobs for this persona's saved searches; each starts its own bid-graph thread."""
    tools = ToolBox(ctx, "scout")
    found: list[dict[str, Any]] = []
    for search in ctx.settings.scout.saved_searches.get(ctx.persona, []):
        page = await tools.call("search_jobs", search)
        for item in page.get("items", []):
            job = await tools.call("get_job", {"job_id": item["job_id"]})
            if not job.get("ok"):
                continue
            view = job["job"]
            text = view["untrusted_text"]
            body = text["text"] if isinstance(text, dict) else str(text)
            title, _, description = body.partition("\n\n")
            record = {**{k: v for k, v in view.items() if k != "untrusted_text"}, "title": title,
                      "description": description,
                      "screening_questions": [q["text"] for q in view.get("untrusted_screening_questions", [])]}
            digest = content_hash(record)
            if seen.is_new(ctx.persona, record["job_id"], digest):
                seen.add(ctx.persona, record["job_id"], digest)
                found.append(record)
    return found


async def main_async(persona: str, scenario: str) -> list[dict[str, Any]]:
    from agent.local_stack import LocalStack, user_for

    with tempfile.TemporaryDirectory() as tmp:
        stack = LocalStack(Path(tmp), scenario=scenario)
        if scenario == "live":
            # release a few days of the stream
            stack.gigsim.state.ctx.sim.tick(72)
        layer = stack.layer(user_for(persona))
        await layer.discover()
        ctx = BidContext(layer=layer, persona=persona)
        return await scout(ctx, SeenStore(get_config().scout.seen_store))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run saved searches once")
    parser.add_argument("--persona", default="ai_ml")
    parser.add_argument("--scenario", choices=["live", "dev"], default="live")
    args = parser.parse_args()
    jobs = asyncio.run(main_async(args.persona, args.scenario))
    print(f"{len(jobs)} new jobs for {args.persona}")
    for job in jobs[:20]:
        print(f"  {job['job_id']}  {job['title'][:70]}")


if __name__ == "__main__":
    main()
