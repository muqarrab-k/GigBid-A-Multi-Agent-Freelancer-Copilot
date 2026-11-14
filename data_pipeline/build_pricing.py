import json
from typing import Any

import pandas as pd

from agent.config import get_config
from data_pipeline.common import PROCESSED_DIR, describe


def with_buckets(df: pd.DataFrame) -> pd.DataFrame:
    """One row per persona tag, untagged -> off_topic."""
    df = df.assign(category=df["persona_tags"].map(lambda t: list(t) if len(t) else ["off_topic"]))
    return df.explode("category")


def job_values(jobs: pd.DataFrame) -> pd.DataFrame:
    hourly_mid = jobs[["hourly_min", "hourly_max"]].mean(axis=1)
    value = jobs["budget_max"].where(jobs["budget_type"] == "fixed", hourly_mid)
    out = jobs.assign(value=value, source="jobs")
    return out[out["budget_type"].notna() & out["value"].notna()]


def contract_values(contracts: pd.DataFrame) -> pd.DataFrame:
    fixed = (contracts["contract_type"] == "fixed") & (contracts["status"] == "ended")
    value = contracts["total_paid"].where(fixed, contracts["hourly_rate"])
    out = contracts.assign(value=value, budget_type=contracts["contract_type"], source="contracts")
    out["experience_level"] = None
    keep = (out["contract_type"] == "hourly") | fixed
    return out[keep & (out["value"] > 0)]


def cells(df: pd.DataFrame, min_count: int) -> list[dict[str, Any]]:
    """Base cells, plus experience cells where known."""
    keys = ["source", "category", "budget_type"]
    known = df[df["experience_level"].notna()]
    rows = []
    for frame, cols in ((df, keys), (known, [*keys, "experience_level"])):
        for key, group in frame.groupby(cols):
            stats = describe(group["value"])
            if stats["count"] >= min_count:
                cell = {"experience_level": "any", **dict(zip(cols, key, strict=True))}
                rows.append({**cell, **stats})
    return rows


def main() -> dict[str, Any]:
    cfg = get_config().data
    jobs = pd.read_parquet(PROCESSED_DIR / "jobs.parquet")
    contracts = pd.read_parquet(PROCESSED_DIR / "contracts.parquet")
    values = pd.concat([job_values(jobs), contract_values(contracts)], ignore_index=True)
    values = values[["source", "budget_type", "experience_level", "value", "persona_tags"]]
    everything = values.assign(category="all")
    table = cells(pd.concat([with_buckets(values), everything]), cfg.pricing_min_count)

    stats = {
        "currency": "USD",
        "min_count": cfg.pricing_min_count,
        "value": {
            "jobs.fixed": "posted budget",
            "jobs.hourly": "midpoint of posted hourly range",
            "contracts.fixed": "total_paid of ended fixed contracts",
            "contracts.hourly": "hourly_rate",
        },
        "category": "persona tag from data_pipeline/persona_keywords.yaml (off_topic if none)",
        "cells": table,
    }
    (PROCESSED_DIR / "pricing_stats.json").write_text(json.dumps(stats, indent=2))
    print(f"  pricing cells: {len(table)}")
    return stats


if __name__ == "__main__":
    main()
