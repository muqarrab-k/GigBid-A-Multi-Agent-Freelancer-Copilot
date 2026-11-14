import json
import os
import random
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from gigsim.policy import load_policy
from gigsim.settings import ROOT, Settings
from gigsim.store import Store, iso

PUBLIC_JOB_FIELDS = [
    "job_id", "title", "description", "skills", "category", "budget_type", "budget_min",
    "budget_max", "hourly_min", "hourly_max", "currency", "client_id", "client_country",
    "experience_level",
]
TEMPLATES_PATH = ROOT / "templates.yaml"
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


@lru_cache(maxsize=1)
def load_templates() -> dict[str, Any]:
    templates: dict[str, Any] = yaml.safe_load(TEMPLATES_PATH.read_text())
    return templates


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def next_weekday(moment: datetime, weekday: str) -> datetime:
    """Next midnight on the given weekday, strictly after moment."""
    target = WEEKDAYS.index(weekday)
    day = moment.replace(hour=0, minute=0, second=0, microsecond=0)
    days = (target - day.weekday()) % 7 or 7
    return day + timedelta(days=days)


def screening(rng: random.Random, share: float, questions: list[str]) -> list[str]:
    if rng.random() >= share:
        return []
    return rng.sample(questions, rng.choice([1, 2]))


def load_accounts(store: Store, seed_dir: Path) -> None:
    accounts = yaml.safe_load((seed_dir / "accounts.yaml").read_text())
    with store.transaction() as conn:
        for a in accounts:
            token = os.getenv(a["token_env"]) or a["token_default"]
            conn.execute(
                "INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?)",
                (a["account_id"], a["persona"], a["name"], token, a["weekly_connects"], a["weekly_connects"]),
            )


def load_clients(store: Store, seed_dir: Path) -> None:
    with store.transaction() as conn:
        for row in read_jsonl(seed_dir / "clients.jsonl"):
            conn.execute("INSERT INTO clients VALUES (?, ?)", (row["client_id"], json.dumps(row)))
        for row in read_jsonl(seed_dir / "client_secrets.jsonl"):
            conn.execute("INSERT INTO client_secrets VALUES (?, ?)", (row["client_id"], json.dumps(row)))


def insert_job(conn: Any, job: dict[str, Any], status: str, release_at: str | None,
               posted_at: str | None, questions: list[str]) -> None:
    public = {k: job.get(k) for k in PUBLIC_JOB_FIELDS}
    public["screening_questions"] = questions
    conn.execute(
        "INSERT OR IGNORE INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (job["job_id"], job.get("client_id"), status, release_at, posted_at, job["title"],
         job.get("description") or "", json.dumps(job.get("skills") or []), job.get("budget_type"),
         job.get("budget_max"), job.get("hourly_max"), json.dumps(public)),
    )


def load_jobs(store: Store, settings: Settings, scenario: str, rng: random.Random, start: datetime) -> None:
    seed_dir = settings.path(settings.seed_dir)
    questions = load_templates()["screening_questions"]
    history = read_jsonl(seed_dir / "jobs_history.jsonl")
    with store.transaction() as conn:
        for job in history:
            posted = (job.get("posted_at") or iso(start - timedelta(days=30)))[:19] + "Z"
            insert_job(conn, job, "closed", None, posted, [])
        if scenario == "dev":
            for job in read_jsonl(seed_dir / "jobs_dev_pool.jsonl"):
                insert_job(conn, job, "open", iso(start), iso(start),
                           screening(rng, settings.screening_share, questions))
            return
        window = settings.stream_release_days * 24 * 3600
        stream = read_jsonl(seed_dir / "jobs_stream.jsonl")
        offsets = sorted(rng.uniform(0, window) for _ in stream)
        for job, offset in zip(stream, offsets, strict=True):
            when = iso(start + timedelta(seconds=int(offset)))
            insert_job(conn, job, "pending", when, None,
                       screening(rng, settings.screening_share, questions))


def reset(store: Store, settings: Settings, scenario: str | None = None, seed: int | None = None) -> dict[str, Any]:
    """Fresh database for a scenario."""
    scenario = scenario or settings.scenario
    seed = settings.seed if seed is None else seed
    start = settings.start_time
    policy = load_policy(settings.path(settings.policies_dir), settings.policy)
    store.recreate()
    for key, value in {
        "scenario": scenario,
        "seed": seed,
        "now": iso(start),
        "policy": settings.policy,
        "next_refill": iso(next_weekday(start, policy.connects.refill_weekday)),
    }.items():
        store.set_meta(key, value)
    seed_dir = settings.path(settings.seed_dir)
    load_accounts(store, seed_dir)
    load_clients(store, seed_dir)
    load_jobs(store, settings, scenario, random.Random(f"{seed}|jobs"), start)
    return {"scenario": scenario, "seed": seed, "sim_time": iso(start)}
