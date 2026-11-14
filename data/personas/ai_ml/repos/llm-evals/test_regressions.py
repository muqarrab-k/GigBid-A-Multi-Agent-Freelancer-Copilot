import json
from pathlib import Path

import pytest

from llm_evals.scoring import average_rubric_score, score_responses


FIXTURE_DIR = Path(__file__).parent / "fixtures"
BASELINE_PATH = FIXTURE_DIR / "rubric_baseline.json"


def load_baseline():
    with BASELINE_PATH.open() as f:
        return json.load(f)


def test_baseline_fixture_exists():
    assert BASELINE_PATH.exists(), "missing regression baseline fixture"


def test_average_rubric_score_does_not_drop():
    baseline = load_baseline()
    current = score_responses(
        baseline["items"],
        model=baseline["model"],
        backend=baseline.get("backend", "vllm"),
    )
    # Compare against the saved release baseline.
    assert average_rubric_score(current) >= pytest.approx(baseline["average_score"], rel=0, abs=1e-6)


def test_score_distribution_is_reasonable():
    baseline = load_baseline()
    scored = score_responses(
        baseline["items"],
        model=baseline["model"],
        backend=baseline.get("backend", "vllm"),
    )

    scores = [item["rubric_score"] for item in scored]
    assert len(scores) == len(baseline["items"])
    assert min(scores) >= 0
    assert max(scores) <= 1.0
    assert average_rubric_score(scored) >= baseline["minimum_acceptable_average"]


@pytest.mark.parametrize("item_index", [0, 50, 100, 150, 200])
def test_sample_items_remain_scored(item_index):
    baseline = load_baseline()
    item = baseline["items"][item_index]

    scored = score_responses([item], model=baseline["model"], backend=baseline.get("backend", "vllm"))
    assert len(scored) == 1
    assert scored[0]["rubric_score"] is not None
