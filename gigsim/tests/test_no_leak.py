import json
from pathlib import Path
from typing import Any

from fastapi.routing import APIRoute

from gigsim.tests.conftest import ADMIN, AI, MakeClient, open_jobs, store, submit_proposal

REPO = Path(__file__).resolve().parents[2]
SEED = REPO / "gigsim" / "seed"
DATASETS = REPO / "evals" / "datasets"
SAFE_KEYS = {"job_id", "client_id", "split", "persona", "synthetic"}
LEAK_VALUES = ["generic_opening", "too_long", "no_relevant_example", "upfront_questions",
               "is_scammer", "reply_tendency", "must_have_skills", "budget_ceiling",
               "relevant_evidence_ids", "fair_price_band", "has_injection", "is_scam", "plant_log"]


def first_row_keys(path: Path) -> set[str]:
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return set().union(*(set(r) for r in rows)) if rows else set()


def forbidden_keys() -> set[str]:
    keys = first_row_keys(SEED / "client_secrets.jsonl")
    keys |= first_row_keys(DATASETS / "plant_log.jsonl")
    keys |= first_row_keys(DATASETS / "dev" / "labels.jsonl")
    keys |= {"score", "decide_at", "final_at", "intent", "injected", "token"}
    return keys - SAFE_KEYS


def walk_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | set().union(*(walk_keys(v) for v in value.values()))
    if isinstance(value, list):
        return set().union(*(walk_keys(v) for v in value)) if value else set()
    return set()


def test_no_endpoint_leaks_gold_fields(make_client: MakeClient) -> None:
    c = make_client()
    store(c).execute("UPDATE accounts SET connects = 1000")
    jobs = open_jobs(c, 10)
    for i, job in enumerate(jobs):
        submit_proposal(c, job, f"leak{i}")
    c.post("/admin/tick", json={"hours": 72}, headers=ADMIN)
    threads = c.get("/threads", headers=AI).json()
    if not threads:
        ctx = c.app.state.ctx  # type: ignore[attr-defined]
        first = ctx.store.one("SELECT * FROM proposals LIMIT 1")
        tid = ctx.sim.open_thread(first, jobs[0]["client_id"])
        ctx.sim.post_client_message(tid, "question", None, "acct_ai_ml")
        threads = c.get("/threads", headers=AI).json()
    thread_id = threads[0]["thread_id"]
    c.post(f"/threads/{thread_id}/messages", headers={**AI, "Idempotency-Key": "m"},
           json={"text": "Happy to answer, here is how I would start."})
    c.post("/admin/tick", json={"hours": 200}, headers=ADMIN)
    proposal_id = c.get("/proposals", headers=AI).json()["items"][0]["proposal_id"]

    calls = {
        "/health": c.get("/health"),
        "/policy": c.get("/policy"),
        "/jobs": c.get("/jobs", params={"status": "any", "limit": 100}, headers=AI),
        "/jobs/{job_id}": c.get(f"/jobs/{jobs[0]['job_id']}", headers=AI),
        "/clients/{client_id}": c.get(f"/clients/{jobs[0]['client_id']}", headers=AI),
        "/me": c.get("/me", headers=AI),
        "/me/connects": c.get("/me/connects", headers=AI),
        "/proposals": c.get("/proposals", params={"limit": 100}, headers=AI),
        "/proposals/{proposal_id}": c.get(f"/proposals/{proposal_id}", headers=AI),
        "/threads": c.get("/threads", headers=AI),
        "/threads/{thread_id}/messages": c.get(f"/threads/{thread_id}/messages", headers=AI),
        "/events": c.get("/events", params={"limit": 100}, headers=AI),
        "/admin/stats": c.get("/admin/stats", headers=ADMIN),
    }
    routes = c.app.routes  # type: ignore[attr-defined]
    gets = {r.path for r in routes if isinstance(r, APIRoute) and "GET" in (r.methods or set())}
    assert gets <= set(calls), f"new GET route not scanned: {gets - set(calls)}"

    bad_keys = forbidden_keys()
    for path, response in calls.items():
        assert response.status_code == 200, path
        body = response.json()
        leaked = walk_keys(body) & bad_keys
        assert not leaked, f"{path} leaks {leaked}"
        text = json.dumps(body)
        assert not [v for v in LEAK_VALUES if v in text], path
