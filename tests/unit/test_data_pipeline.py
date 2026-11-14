import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pydantic import ValidationError

from agent.config import ConnectsRule, DataConfig, SplitSizes, load_config
from data_pipeline.clean import (
    clean_text,
    detect_currency,
    dup_groups,
    exact_key,
    near_key,
    parse_money,
    parse_range,
    stable_id,
)
from data_pipeline.common import describe, shares
from data_pipeline.persona import persona_tags
from data_pipeline.schema import ContractRecord, MarketJob, ScamExample
from data_pipeline.seed_split import bucket_targets, split_jobs, write_jsonl


def test_clean_text_strips_html_and_space() -> None:
    raw = "<p>Build a&nbsp;<b>React</b> app</p>\n\n<ul><li>fast</li></ul>"
    assert clean_text(raw) == "Build a React app fast"
    assert clean_text("   ") is None
    assert clean_text(None) is None
    assert clean_text(float("nan")) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("$1,200.50", 1200.5), ("500", 500.0), (35, 35.0), ("Budget: $50", 50.0), ("n/a", None)],
)
def test_parse_money(raw: object, expected: float | None) -> None:
    assert parse_money(raw) == expected


def test_parse_money_ignores_nan_and_none() -> None:
    assert parse_money(float("nan")) is None
    assert parse_money(None) is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("$15.00-$35.00", (15.0, 35.0)),
        ("$35 - $15", (15.0, 35.0)),
        ("$20", (20.0, 20.0)),
        (40.0, (40.0, 40.0)),
        ("Not sure", (None, None)),
        (None, (None, None)),
    ],
)
def test_parse_range(raw: object, expected: tuple[float | None, float | None]) -> None:
    assert parse_range(raw) == expected


def test_detect_currency() -> None:
    assert detect_currency("$40") == "USD"
    assert detect_currency("€40") == "EUR"
    assert detect_currency("40 GBP") == "GBP"
    assert detect_currency("40") == "USD"


def test_identical_texts_share_group() -> None:
    title, desc = "Build a churn model", "Need a Python baseline for churn."
    keys = [exact_key(title, desc), exact_key(" build A churn model ", desc), exact_key("Logo", "x")]
    near = [near_key(title, desc), near_key(title, desc), near_key("Logo", "x")]
    groups = dup_groups(keys, near)
    assert groups[0] == groups[1]
    assert groups[0] != groups[2]


def test_near_duplicates_share_group() -> None:
    base = "Need a Python developer to build a scraper for 500 product pages " * 3
    edited = base.replace("500", "800") + " Thanks!"
    keys = [exact_key("Scraper", base), exact_key("Scraper", edited)]
    near = [near_key("Scraper", base), near_key("Scraper", edited)]
    assert keys[0] != keys[1]
    assert len(set(dup_groups(keys, near))) == 1


def test_dup_groups_are_transitive() -> None:
    groups = dup_groups(["a", "a", "b", "c"], ["x", "y", "y", "z"])
    assert groups[0] == groups[1] == groups[2]
    assert groups[3] != groups[0]


def test_stable_id_is_normalised() -> None:
    assert stable_id("Hello, World", 1) == stable_id("hello world", "1")
    assert len(stable_id("x")) == 16


@pytest.mark.parametrize(
    ("title", "skills", "desc", "expected"),
    [
        ("Fine-tune an LLM for support chat", ["Python"], "", ["ai_ml"]),
        ("React and Node.js dashboard app", [], "", ["fullstack", "data_analyst"]),
        ("Monthly report", ["Power BI", "SQL"], "", ["data_analyst"]),
        ("Logo design for bakery", ["Illustrator"], "Make it pink.", []),
        ("Help needed", [], "We use machine learning and pytorch daily.", ["ai_ml"]),
    ],
)
def test_persona_tags(title: str, skills: list[str], desc: str, expected: list[str]) -> None:
    assert persona_tags(title, skills, desc) == expected


def test_persona_needs_word_boundaries() -> None:
    assert persona_tags("Paint my house", ["Painting"], "email me") == []


def job(**kw: object) -> dict[str, object]:
    base = {"job_id": "abcdef1234567890", "source": "jobs_2024_50k", "title": "Build app"}
    return {**base, **kw}


def test_market_job_validates() -> None:
    item = MarketJob.model_validate(job(budget_type="fixed", budget_min=100, budget_max=200))
    assert item.currency == "USD"
    assert item.description is None


@pytest.mark.parametrize(
    "bad",
    [
        {"budget_min": 300, "budget_max": 100},
        {"hourly_min": -5},
        {"budget_type": "weekly"},
        {"title": ""},
        {"persona_tags": ["designer"]},
        {"made_up": 1},
    ],
)
def test_market_job_rejects_bad_values(bad: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        MarketJob.model_validate(job(**bad))


def test_scam_example_labels() -> None:
    assert ScamExample(text="Pay a fee first", label="fake", source="fake_jobs").label == "fake"
    with pytest.raises(ValidationError):
        ScamExample(text="x", label="maybe", source="fake_jobs")  # type: ignore[arg-type]


def test_connects_rule_from_config() -> None:
    rule = load_config().bidding_rules.connects_rule
    assert rule.connects_for("hourly", None) == rule.hourly_default
    assert rule.connects_for(None, None) == rule.unknown_default
    cheap, pricey = rule.connects_for("fixed", 1), rule.connects_for("fixed", 1_000_000)
    assert cheap <= pricey == rule.fixed_tiers[-1].connects


def fake_jobs(n_groups: int = 120) -> pd.DataFrame:
    rows = []
    personas = [["ai_ml"], ["fullstack"], ["data_analyst"], []]
    for g in range(n_groups):
        copies = 1 + g % 3
        for c in range(copies):
            rows.append(
                {
                    "job_id": f"job{g:04d}{c}",
                    "source": "fixture",
                    "title": f"title {g}",
                    "description": "x" * (10 + c),
                    "persona_tags": personas[g % 4],
                    "budget_type": "fixed" if g % 2 else "hourly",
                    "dup_group": f"grp{g:04d}",
                }
            )
    return pd.DataFrame(rows)


def small_cfg(seed: int = 7) -> DataConfig:
    sizes = SplitSizes(history=20, stream=8, dev_pool=12)
    return DataConfig(
        seed=seed,
        split_sizes=sizes,
        off_topic_share=0.25,
        stream_dup_cap=3,
        min_description_words=0,
        max_fixed_budget=100_000,
        max_hourly_rate=500,
        contract_date_min="2000-01-01",  # type: ignore[arg-type]
        contract_date_max="2024-12-31",  # type: ignore[arg-type]
    )


def test_splits_disjoint_by_group() -> None:
    splits = split_jobs(fake_jobs(), small_cfg())
    groups = [set(df["dup_group"]) for df in splits.values()]
    assert not groups[0] & groups[1]
    assert not groups[0] & groups[2]
    assert not groups[1] & groups[2]
    assert splits["history"]["dup_group"].is_unique
    assert len(splits["stream"]) > splits["stream"]["dup_group"].nunique()


def test_splits_are_deterministic_and_seeded() -> None:
    a = split_jobs(fake_jobs(), small_cfg())
    b = split_jobs(fake_jobs(), small_cfg())
    c = split_jobs(fake_jobs(), small_cfg(seed=8))
    for name in a:
        assert a[name]["job_id"].tolist() == b[name]["job_id"].tolist()
    assert a["history"]["job_id"].tolist() != c["history"]["job_id"].tolist()


def test_splits_are_balanced() -> None:
    targets = bucket_targets(20, 0.25)
    assert sum(targets.values()) == 20
    assert targets["off_topic"] == 5
    history = split_jobs(fake_jobs(), small_cfg())["history"]
    assert len(history) == 20


def test_near_key_needs_enough_words() -> None:
    assert near_key("Logo", "make it pink") is None
    assert near_key("Logo", None) is None


def test_title_only_key_uses_extra_fields() -> None:
    assert exact_key("Data Entry", None, "US", 5.0) == exact_key("data entry", None, "US", 5.0)
    assert exact_key("Data Entry", None, "US", 5.0) != exact_key("Data Entry", None, "UK", 5.0)


def test_contract_record_rules() -> None:
    base = {
        "contract_id": "abcdef1234567890",
        "title": "Translate a doc",
        "status": "ended",
        "total_hours": 3.5,
        "total_paid": 122.5,
        "freelancer_id": "~01",
    }
    assert ContractRecord(contract_type="hourly", hourly_rate=35, **base).hourly_rate == 35
    with pytest.raises(ValidationError):
        ContractRecord(contract_type="hourly", **base)
    with pytest.raises(ValidationError):
        ContractRecord(contract_type="fixed", **{**base, "total_paid": -1})


def test_connects_tiers_must_be_sorted() -> None:
    with pytest.raises(ValidationError):
        ConnectsRule(
            hourly_default=8,
            unknown_default=8,
            fixed_tiers=[{"max_budget": 500, "connects": 8}, {"max_budget": 50, "connects": 4}],
        )


def test_describe_and_shares() -> None:
    stats = describe(pd.Series([1, 2, 3, 4, None]))
    assert stats["count"] == 4
    assert stats["p50"] == 2.5
    assert describe(pd.Series([], dtype=float)) == {"count": 0}
    assert shares(pd.Series(["a", "a", None, "b"])) == {"a": 0.5, "missing": 0.25, "b": 0.25}


def test_seed_rows_write_as_valid_json(tmp_path: Path) -> None:
    df = pd.DataFrame(
        [
            {
                "job_id": "abcdef1234567890",
                "source": "fixture",
                "title": "Build app",
                "currency": "USD",
                "description": None,
                "skills": np.array(["React"]),
                "persona_tags": np.array(["fullstack"]),
                "budget_max": float("nan"),
                "connects_cost": 8.0,
                "posted_at": pd.NaT,
            }
        ]
    )
    for field in MarketJob.model_fields:
        if field not in df:
            df[field] = None
    path = tmp_path / "jobs.jsonl"
    write_jsonl(df, str(path))
    row = json.loads(path.read_text())
    assert row["skills"] == ["React"]
    assert row["budget_max"] is None
    assert row["connects_cost"] == 8
