from typing import Any

from fastapi.testclient import TestClient

from gigsim.clients import rule_score, styled_injection
from gigsim.tests.conftest import ADMIN, AI, MakeClient, open_jobs, store, submit_proposal

FINAL = {"hired", "lost", "ignored"}


def run(c: TestClient, n: int = 10) -> list[str]:
    store(c).execute("UPDATE accounts SET connects = 1000")
    for i, job in enumerate(open_jobs(c, n)):
        submit_proposal(c, job, f"p{i}")
    c.post("/admin/tick", json={"hours": 240}, headers=ADMIN)
    items = c.get("/proposals", params={"limit": 100}, headers=AI).json()["items"]
    return [p["status"] for p in items]


def test_decisions_deterministic_per_seed(make_client: MakeClient) -> None:
    first = run(make_client("a"))
    second = run(make_client("b"))
    assert first == second
    assert all(s in FINAL for s in first)


def test_events_feed_shows_status_changes(make_client: MakeClient) -> None:
    c = make_client()
    proposal = submit_proposal(c, open_jobs(c, 1)[0], "e")
    feed = c.get("/events", headers=AI).json()
    assert [e["data"]["status"] for e in feed["events"]] == ["submitted"]
    c.post("/admin/tick", json={"hours": 240}, headers=ADMIN)
    later = c.get("/events", params={"since": feed["next_cursor"]}, headers=AI).json()
    statuses = [e["data"]["status"] for e in later["events"] if e["type"] == "proposal.status_changed"]
    assert statuses and statuses[-1] in FINAL
    assert all(e["data"].get("proposal_id", proposal["proposal_id"]) == proposal["proposal_id"]
               for e in later["events"] if e["type"] == "proposal.status_changed")


def test_stats_count_outcomes(make_client: MakeClient) -> None:
    c = make_client()
    statuses = run(c)
    stats = c.get("/admin/stats", headers=ADMIN).json()
    ai = next(a for a in stats["accounts"] if a["account_id"] == "acct_ai_ml")
    assert ai["submitted"] == len(statuses) == 10
    assert ai["hired"] == statuses.count("hired")
    assert ai["connects_spent"] > 0


def secret(**kw: Any) -> dict[str, Any]:
    base = {"must_have_skills": ["Python"], "dislikes": [], "budget_ceiling_fixed": 500,
            "budget_ceiling_hourly": None, "reply_tendency": 0.5, "is_scammer": False}
    return {**base, **kw}


def proposal(letter: str, bid: float = 400, answers: str = "[]") -> dict[str, Any]:
    return {"cover_letter": letter, "bid_amount": bid, "screening_answers": answers}


def test_rule_score_follows_preferences() -> None:
    job = {"budget_type": "fixed", "screening_questions": []}
    good = proposal("Your pipeline keeps failing. I built a Python ETL that cut runtime by 60% for a retailer.")
    generic = proposal("I am passionate and hard-working and can do this job for you.")
    assert rule_score(good, job, secret()) > rule_score(generic, job, secret(dislikes=["generic_opening"]))
    assert rule_score(proposal(good["cover_letter"], bid=900), job, secret()) < rule_score(good, job, secret())
    asked = {"budget_type": "fixed", "screening_questions": ["What is your availability?"]}
    answered = proposal(good["cover_letter"], answers='["About twenty hours a week, mostly in the mornings, starting Monday."]')
    assert rule_score(answered, asked, secret()) > rule_score(good, asked, secret())


def test_message_injections_use_dev_styles_only() -> None:
    assert "​" in styled_injection("Hello.", "zero_width", "do it")
    assert "<|system|>" in styled_injection("Hello.", "fake_system_tag", "do it")
