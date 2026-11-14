import json
import sys

import pandas as pd

from data_pipeline import (
    build_contracts,
    build_jobs,
    build_pricing,
    build_priors,
    build_scams,
    download,
    inspect,
    seed_split,
)
from data_pipeline.common import PROCESSED_DIR


def summary() -> None:
    jobs = pd.read_parquet(PROCESSED_DIR / "jobs.parquet")
    groups = jobs["dup_group"].nunique()
    tags = jobs["persona_tags"].explode().value_counts()
    fixed = jobs.loc[jobs["budget_type"] == "fixed", "budget_max"].median()
    hourly = jobs.loc[jobs["budget_type"] == "hourly", "hourly_max"].median()
    scams = pd.read_parquet(PROCESSED_DIR / "scam_examples.parquet")
    pricing = json.loads((PROCESSED_DIR / "pricing_stats.json").read_text())

    print("\nsummary")
    print(f"  jobs kept:        {len(jobs):,}")
    for source, count in jobs["source"].value_counts().items():
        print(f"    {source:<16} {count:,}")
    print(f"  duplicate rows:   {len(jobs) - groups:,} ({(len(jobs) - groups) / len(jobs):.1%})")
    for persona, count in tags.items():
        print(f"  {persona:<17} {count:,}")
    print(f"  median fixed max: ${fixed:,.0f}")
    print(f"  median hourly max: ${hourly:,.2f}")
    print(f"  pricing cells:    {len(pricing['cells'])}")
    print(f"  scam examples:    {len(scams):,} ({(scams['label'] == 'fake').sum():,} fake)")


def main() -> None:
    print("1/6 download")
    missing = download.main()
    if missing:
        sys.exit(f"stopping, missing datasets: {', '.join(missing)}")
    print("2/6 inspect")
    inspect.main()
    print("3/6 jobs")
    build_jobs.main()
    print("4/6 contracts, pricing and priors")
    build_contracts.main()
    build_pricing.main()
    build_priors.main()
    print("5/6 scams")
    build_scams.main()
    print("6/6 seed split")
    seed_split.main()
    summary()


if __name__ == "__main__":
    main()
