"""Change request: GigSim policy v2 (Connects doubled above $1,000, 220-word cap) absorbed by config."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from agent.config import ROOT, load_config
from agent.marketplace_port import Policy as PortPolicy
from agent.marketplace_port import precheck
from gigsim.app import create_app
from gigsim.policy import available, load_policy
from gigsim.settings import load_settings

POLICIES = ROOT / "gigsim" / "policies"
AI = {"Authorization": "Bearer dev-ai_ml-token"}
ADMIN = {"Authorization": "Bearer dev-admin-token"}


def letter(words: int) -> str:
    return " ".join(["word"] * words)


@pytest.fixture
def gigsim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    for key in ("GIGSIM_ADMIN_TOKEN", "GIGSIM_TOKEN_AI_ML"):
        monkeypatch.delenv(key, raising=False)
    settings = load_settings(overrides={
        "storage": str(tmp_path / "g.db"), "scenario": "dev", "policy": "v2",
        "chaos": {"error_rate": 0.0, "latency_ms_max": 0},
        "rate_limit": {"capacity": 10_000, "refill_per_second": 1000},
        "clients": {"mode": "rule_only", "llm": {"cache_dir": str(tmp_path / "llm")}},
    })
    with TestClient(create_app(settings)) as client:
        yield client


def fixed_job(client: TestClient, low: float, high: float) -> dict[str, Any]:
    offset: int | None = 0
    while offset is not None:
        page = client.get("/jobs", params={"limit": 100, "offset": offset}, headers=AI).json()
        for job in page["items"]:
            if job["budget_type"] == "fixed" and job["budget_max"] and low < job["budget_max"] <= high:
                return dict(job)
        offset = page["next_offset"]
    raise AssertionError("no such job")


def test_v2_doubles_connects_only_above_1000() -> None:
    v1, v2 = load_policy(POLICIES, "v1"), load_policy(POLICIES, "v2")
    jobs = [{"budget_type": "fixed", "budget_max": b} for b in (800, 1500, 5000)] + [{"budget_type": "hourly"}]
    assert [v1.connects_for(j) for j in jobs] == [12, 12, 16, 12]
    assert [v2.connects_for(j) for j in jobs] == [12, 24, 32, 12]
    assert (v1.proposals.max_words, v2.proposals.max_words) == (500, 220)


def test_admin_switches_policy(gigsim: TestClient) -> None:
    assert gigsim.get("/policy").json()["version"] == "v2"
    assert gigsim.post("/admin/policy", headers=ADMIN, json={"version": "v1"}).status_code == 200
    assert gigsim.get("/policy").json()["version"] == "v1"


def test_gigsim_v2_blocks_long_letters_and_charges_double(gigsim: TestClient) -> None:
    job = fixed_job(gigsim, 1000, 2000)
    assert job["connects_cost"] == 24
    long = gigsim.post("/proposals/drafts", headers={**AI, "Idempotency-Key": "d-long"},
                       json={"job_id": job["job_id"], "cover_letter": letter(250), "bid_amount": job["budget_max"]})
    assert long.json()["policy_check"]["rule_id"] == "proposal_too_long"
    sent = gigsim.post(f"/proposals/{long.json()['proposal_id']}/submit", headers={**AI, "Idempotency-Key": "s-long"})
    assert sent.status_code == 422 and sent.json()["rule_id"] == "proposal_too_long"

    other = fixed_job(gigsim, 2000, 100_000)
    before = gigsim.get("/me/connects", headers=AI).json()["balance"]
    draft = gigsim.post("/proposals/drafts", headers={**AI, "Idempotency-Key": "d-ok"},
                        json={"job_id": other["job_id"], "cover_letter": letter(200), "bid_amount": other["budget_max"]})
    ok = gigsim.post(f"/proposals/{draft.json()['proposal_id']}/submit", headers={**AI, "Idempotency-Key": "s-ok"})
    assert ok.status_code == 200
    assert before - gigsim.get("/me/connects", headers=AI).json()["balance"] == 32


def test_agent_precheck_reads_the_live_policy(gigsim: TestClient) -> None:
    policy = PortPolicy.model_validate(gigsim.get("/policy").json())
    assert precheck(policy, letter(230)) == ("proposal_too_long", "230 words, maximum 220")
    assert precheck(policy, letter(200)) is None


def test_agent_config_fits_every_shipped_policy() -> None:
    """Writer length and the Connects limit stay inside every policy in gigsim/policies/."""
    cfg = load_config()
    for version in available(POLICIES):
        policy = load_policy(POLICIES, version)
        assert policy.proposals.min_words <= cfg.writer.min_words
        assert cfg.writer.max_words <= policy.proposals.max_words
        dearest = max(t.connects for t in policy.connects.fixed_tiers)
        assert dearest <= cfg.bidding_rules.max_connects_per_job
