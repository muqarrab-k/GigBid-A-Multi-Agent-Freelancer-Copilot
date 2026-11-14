import ast
from pathlib import Path

from gigsim.tests.conftest import (
    ADMIN,
    AI,
    FS,
    LETTER,
    MakeClient,
    open_jobs,
    store,
    submit_proposal,
)

GIGSIM = Path(__file__).resolve().parents[1]


def test_search_and_pagination(make_client: MakeClient) -> None:
    c = make_client()
    first = c.get("/jobs", params={"limit": 5}, headers=AI).json()
    second = c.get("/jobs", params={"limit": 5, "offset": 5}, headers=AI).json()
    assert first["total"] == 600 and first["next_offset"] == 5
    assert not {j["job_id"] for j in first["items"]} & {j["job_id"] for j in second["items"]}

    hits = c.get("/jobs", params={"q": "python", "limit": 100}, headers=AI).json()
    assert hits["total"] > 0
    assert all("python" in (j["title"] + (j["description"] or "")).lower() for j in hits["items"])

    rich = c.get("/jobs", params={"budget_type": "fixed", "min_budget": 1000}, headers=AI).json()
    assert all(j["budget_max"] >= 1000 for j in rich["items"])
    tagged = c.get("/jobs", params={"skills": "SQL"}, headers=AI).json()
    assert all("sql" in [s.lower() for s in j["skills"]] for j in tagged["items"])
    assert c.get("/jobs", params={"limit": 0}, headers=AI).status_code == 422


def test_job_and_client_lookup(make_client: MakeClient) -> None:
    c = make_client()
    job = c.get("/jobs", params={"limit": 1}, headers=AI).json()["items"][0]
    assert c.get(f"/jobs/{job['job_id']}", headers=AI).json() == job
    client = c.get(f"/clients/{job['client_id']}", headers=AI)
    assert client.status_code == 200 and "hire_rate" in client.json()
    assert c.get("/jobs/nope", headers=AI).status_code == 404


def test_auth_required(make_client: MakeClient) -> None:
    c = make_client()
    assert c.get("/jobs").status_code == 401
    assert c.get("/me", headers={"Authorization": "Bearer wrong"}).json()["error"] == "unauthorized"
    assert c.post("/admin/tick", json={"hours": 1}, headers=AI).status_code == 401
    assert c.get("/health").status_code == 200
    assert c.get("/me", headers=AI).json()["account_id"] == "acct_ai_ml"


def test_idempotent_submit_never_double_charges(make_client: MakeClient) -> None:
    c = make_client()
    job = open_jobs(c, 1)[0]
    before = c.get("/me/connects", headers=AI).json()["balance"]
    draft = c.post("/proposals/drafts", headers={**AI, "Idempotency-Key": "d1"},
                   json={"job_id": job["job_id"], "cover_letter": LETTER, "bid_amount": 300})
    again = c.post("/proposals/drafts", headers={**AI, "Idempotency-Key": "d1"},
                   json={"job_id": job["job_id"], "cover_letter": LETTER, "bid_amount": 300})
    assert draft.json() == again.json() and again.headers["Idempotent-Replayed"] == "true"
    pid = draft.json()["proposal_id"]

    one = c.post(f"/proposals/{pid}/submit", headers={**AI, "Idempotency-Key": "s1"})
    two = c.post(f"/proposals/{pid}/submit", headers={**AI, "Idempotency-Key": "s1"})
    assert one.status_code == two.status_code == 200 and one.json() == two.json()
    after = c.get("/me/connects", headers=AI).json()["balance"]
    assert before - after == one.json()["connects_spent"] == job["connects_cost"]

    other_key = c.post(f"/proposals/{pid}/submit", headers={**AI, "Idempotency-Key": "s2"})
    assert other_key.status_code == 409 and other_key.json()["error"] == "already_submitted"
    reused = c.post("/proposals/drafts", headers={**AI, "Idempotency-Key": "d1"},
                    json={"job_id": job["job_id"], "cover_letter": LETTER, "bid_amount": 999})
    assert reused.json()["error"] == "idempotency_key_reused"
    missing = c.post(f"/proposals/{pid}/submit", headers=AI)
    assert missing.status_code == 400 and missing.json()["error"] == "idempotency_key_required"


def test_insufficient_connects(make_client: MakeClient) -> None:
    c = make_client()
    store(c).execute("UPDATE accounts SET connects = 1 WHERE account_id = 'acct_ai_ml'")
    job = open_jobs(c, 1)[0]
    draft = c.post("/proposals/drafts", headers={**AI, "Idempotency-Key": "d"},
                   json={"job_id": job["job_id"], "cover_letter": LETTER, "bid_amount": 100}).json()
    r = c.post(f"/proposals/{draft['proposal_id']}/submit", headers={**AI, "Idempotency-Key": "s"})
    assert r.status_code == 402
    assert r.json()["error"] == "insufficient_connects" and r.json()["balance"] == 1


def test_rate_limit_returns_429(make_client: MakeClient) -> None:
    c = make_client(rate_limit={"capacity": 3, "refill_per_second": 0.01})
    codes = [c.get("/me", headers=AI).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    limited = c.get("/me", headers=AI)
    assert int(limited.headers["Retry-After"]) >= 1
    assert c.get("/me", headers=FS).status_code == 200


def test_seeded_5xx_is_deterministic(make_client: MakeClient) -> None:
    runs = []
    for name in ("a", "b"):
        c = make_client(name, chaos={"error_rate": 0.3, "latency_ms_max": 0})
        runs.append([c.get("/me", headers=AI).status_code for _ in range(30)])
    assert runs[0] == runs[1]
    assert 503 in runs[0] and 200 in runs[0]


def test_policy_violations_name_the_rule(make_client: MakeClient) -> None:
    c = make_client()
    jobs = open_jobs(c, 2)
    letter = LETTER + " Reach me at noor.halden@example.com for details."
    draft = c.post("/proposals/drafts", headers={**AI, "Idempotency-Key": "d"},
                   json={"job_id": jobs[0]["job_id"], "cover_letter": letter, "bid_amount": 100}).json()
    assert draft["policy_check"]["rule_id"] == "no_email"
    r = c.post(f"/proposals/{draft['proposal_id']}/submit", headers={**AI, "Idempotency-Key": "s"})
    assert r.status_code == 422 and r.json()["error"] == "policy_violation" and r.json()["rule_id"] == "no_email"

    short = c.post("/proposals/drafts", headers={**AI, "Idempotency-Key": "d2"},
                   json={"job_id": jobs[1]["job_id"], "cover_letter": "I can do it.", "bid_amount": 50}).json()
    r = c.post(f"/proposals/{short['proposal_id']}/submit", headers={**AI, "Idempotency-Key": "s2"})
    assert r.json()["rule_id"] == "proposal_too_short"


def test_daily_submission_limit(make_client: MakeClient) -> None:
    c = make_client()
    store(c).execute("UPDATE accounts SET connects = 1000")
    jobs = open_jobs(c, 11)
    for i, job in enumerate(jobs[:10]):
        submit_proposal(c, job, f"k{i}")
    draft = c.post("/proposals/drafts", headers={**AI, "Idempotency-Key": "d-last"},
                   json={"job_id": jobs[10]["job_id"], "cover_letter": LETTER, "bid_amount": 50}).json()
    r = c.post(f"/proposals/{draft['proposal_id']}/submit", headers={**AI, "Idempotency-Key": "s-last"})
    assert r.status_code == 422 and r.json()["rule_id"] == "max_submissions_per_day"


def test_validation_errors_are_clear(make_client: MakeClient) -> None:
    c = make_client()
    r = c.post("/proposals/drafts", headers={**AI, "Idempotency-Key": "x"},
               json={"job_id": "j", "cover_letter": "hi", "bid_amount": -5})
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "validation_error" and body["detail"][0]["loc"][-1] == "bid_amount"


def test_tick_releases_stream_jobs(make_client: MakeClient) -> None:
    c = make_client(scenario="live")
    assert c.get("/jobs", headers=AI).json()["total"] == 0
    c.post("/admin/tick", json={"hours": 24 * 3}, headers=ADMIN)
    some = c.get("/jobs", headers=AI).json()["total"]
    c.post("/admin/tick", json={"hours": 24 * 12}, headers=ADMIN)
    everything = c.get("/jobs", headers=AI).json()["total"]
    assert 0 < some < everything == 415
    assert c.get("/jobs", params={"status": "closed"}, headers=AI).json()["total"] == 1500


def test_weekly_refill(make_client: MakeClient) -> None:
    c = make_client()
    store(c).execute("UPDATE accounts SET connects = 3")
    c.post("/admin/tick", json={"hours": 24 * 7}, headers=ADMIN)
    assert c.get("/me/connects", headers=AI).json()["balance"] == 80


def test_admin_policy_switch(make_client: MakeClient) -> None:
    c = make_client()
    assert c.post("/admin/policy", json={"version": "v9"}, headers=ADMIN).status_code == 422
    assert c.post("/admin/policy", json={"version": "v1"}, headers=ADMIN).json() == {"policy": "v1"}
    assert c.get("/policy").json()["version"] == "v1"


def test_gigsim_imports_nothing_from_the_agent_side() -> None:
    for path in GIGSIM.rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else (
                [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
            for name in names:
                assert name.split(".")[0] not in {"agent", "rag", "apps", "synth", "data_pipeline"}, path
