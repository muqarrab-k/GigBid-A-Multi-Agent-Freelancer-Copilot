from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gigsim.app import create_app
from gigsim.settings import load_settings
from gigsim.store import Store

AI = {"Authorization": "Bearer dev-ai_ml-token"}
FS = {"Authorization": "Bearer dev-fullstack-token"}
ADMIN = {"Authorization": "Bearer dev-admin-token"}

LETTER = (
    "Your churn dashboard needs reliable weekly numbers. I built a similar retention model in "
    "Python with scikit-learn and SQL for a SaaS client, which lifted the top-decile capture by 3.1x "
    "and cut manual reporting by 70%. I would start by auditing the data sources, then ship a first "
    "version within a week and iterate with you on the metrics that matter most."
)

MakeClient = Callable[..., TestClient]


@pytest.fixture(autouse=True)
def no_env_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("GIGSIM_ADMIN_TOKEN", "GIGSIM_TOKEN_AI_ML", "GIGSIM_TOKEN_FULLSTACK",
                "GIGSIM_TOKEN_DATA_ANALYST", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def make_client(tmp_path: Path) -> Iterator[MakeClient]:
    made: list[TestClient] = []

    def build(name: str = "g", **overrides: Any) -> TestClient:
        base = {
            "storage": str(tmp_path / f"{name}.db"),
            "scenario": "dev",
            "chaos": {"error_rate": 0.0, "latency_ms_max": 0},
            "rate_limit": {"capacity": 10_000, "refill_per_second": 1000},
            "clients": {"mode": "rule_only", "llm": {"cache_dir": str(tmp_path / "llm")}},
        }
        client = TestClient(create_app(load_settings(overrides=merge(base, overrides))))
        made.append(client)
        return client

    yield build
    for client in made:
        client.close()


def merge(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in extra.items():
        out[key] = merge(out[key], value) if isinstance(value, dict) and isinstance(out.get(key), dict) else value
    return out


def store(client: TestClient) -> Store:
    s: Store = client.app.state.ctx.store  # type: ignore[attr-defined]
    return s


def open_jobs(client: TestClient, n: int, headers: dict[str, str] = AI) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    offset = 0
    while len(jobs) < n:
        page = client.get("/jobs", params={"limit": 100, "offset": offset}, headers=headers).json()
        jobs += [j for j in page["items"] if not j["screening_questions"]]
        if page["next_offset"] is None:
            break
        offset = page["next_offset"]
    return jobs[:n]


def submit_proposal(client: TestClient, job: dict[str, Any], key: str, headers: dict[str, str] = AI,
                    letter: str = LETTER) -> dict[str, Any]:
    bid = job["budget_max"] or job["hourly_max"] or 40
    draft = client.post("/proposals/drafts", headers={**headers, "Idempotency-Key": f"d-{key}"},
                        json={"job_id": job["job_id"], "cover_letter": letter, "bid_amount": bid})
    assert draft.status_code == 201, draft.text
    pid = draft.json()["proposal_id"]
    sent = client.post(f"/proposals/{pid}/submit", headers={**headers, "Idempotency-Key": f"s-{key}"})
    assert sent.status_code == 200, sent.text
    body: dict[str, Any] = sent.json()
    return body
