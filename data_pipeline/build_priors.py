import json
from typing import Any

import pandas as pd
import yaml

from data_pipeline.build_jobs import job_key
from data_pipeline.common import PROCESSED_DIR, RAW_DIR, describe, shares
from data_pipeline.persona import KEYWORDS_PATH

FREELANCER_NUMBERS = [
    "years_experience",
    "num_skills",
    "profile_completeness",
    "hourly_rate_usd",
    "total_jobs_completed",
    "job_success_rate",
    "repeat_client_rate",
    "avg_response_time_hrs",
    "total_earnings_12m_usd",
    "success_score",
]
FREELANCER_FLAGS = ["has_portfolio", "has_video_profile", "has_certifications", "churn_risk"]


def client_priors_from_jobs() -> dict[str, Any]:
    df = pd.read_csv(RAW_DIR / "jobs_2023_60k" / "Final_Upwork_Dataset.csv", low_memory=False)
    key = job_key(df["Job_URL"])
    df = df[key.isna() | ~key.duplicated()]
    spent = df["Spent($)"]
    return {
        "origin": "REAL",
        "source": "jobs_2023_60k (client stats shown on each job post, Feb-Mar 2023)",
        "unit": "job post (a client posting many jobs is counted many times)",
        "rows": int(len(df)),
        "spent_usd": describe(spent),
        "spent_zero_share": round(float((spent == 0).mean()), 4),
        "rating": describe(df["Rating"]),
        "rating_missing_share": round(float(df["Rating"].isna().mean()), 4),
        "feedback_count": describe(df["Feedback_Num"]),
        "payment_verified": shares(df["Payment_Situation"]),
        "enterprise_share": round(float(df["Enterprise_Client"].notna().mean()), 4),
        "freelancers_needed": shares(df["Freelancers_Num"]),
        "applicants": shares(df["Applicants_Num"]),
        "experience_level": shares(df["EX_level_demand"]),
        "duration": shares(df["Time_Limitation"]),
        "country_top15": shares(df["Client_Country"], top=15),
    }


def client_priors_from_contracts() -> dict[str, Any]:
    df = pd.read_parquet(PROCESSED_DIR / "contracts.parquet")
    ended_fixed = df[(df["contract_type"] == "fixed") & (df["status"] == "ended")]
    hourly = df[df["contract_type"] == "hourly"]
    per_freelancer = df.groupby("freelancer_id").size()
    return {
        "origin": "REAL",
        "source": "contracts_1_3m",
        "rows": int(len(df)),
        "hourly_share": round(float((df["contract_type"] == "hourly").mean()), 4),
        "ongoing_share": round(float((df["status"] == "ongoing").mean()), 4),
        "zero_paid_share": round(float((df["total_paid"] == 0).mean()), 4),
        "fixed_paid_usd": describe(ended_fixed["total_paid"].where(ended_fixed["total_paid"] > 0)),
        "hourly_rate_usd": describe(hourly["hourly_rate"].where(hourly["hourly_rate"] > 0)),
        "hourly_hours": describe(hourly["total_hours"].where(hourly["total_hours"] > 0)),
        "hourly_paid_usd": describe(hourly["total_paid"].where(hourly["total_paid"] > 0)),
        "duration_days": describe(df["duration_days"]),
        "contracts_per_freelancer": describe(per_freelancer),
        "not_available": "client ids, client spend, ratings, hire rate (no job-to-proposal link)",
    }


def freelancer_block(df: pd.DataFrame) -> dict[str, Any]:
    block: dict[str, Any] = {"rows": int(len(df))}
    for col in FREELANCER_NUMBERS:
        block[col] = describe(df[col])
    for col in FREELANCER_FLAGS:
        block[f"{col}_share"] = round(float(df[col].mean()), 4)
    block["earnings_tier"] = shares(df["earnings_tier"])
    return block


def freelancer_priors() -> dict[str, Any]:
    df = pd.read_csv(RAW_DIR / "freelancer_success" / "freelancer_gig_success_dataset.csv")
    mapping = yaml.safe_load(KEYWORDS_PATH.read_text())["skill_personas"]
    by_skill = {skill: freelancer_block(g) for skill, g in df.groupby("primary_skill")}
    return {
        "origin": "SYNTHETIC",
        "source": "freelancer_success (its author describes it as realistic synthetic records)",
        "skill_personas": mapping,
        "all": freelancer_block(df),
        "by_primary_skill": by_skill,
    }


def main() -> None:
    clients = {"jobs": client_priors_from_jobs(), "contracts": client_priors_from_contracts()}
    (PROCESSED_DIR / "client_priors.json").write_text(json.dumps(clients, indent=2))
    (PROCESSED_DIR / "freelancer_priors.json").write_text(
        json.dumps(freelancer_priors(), indent=2)
    )
    print("  wrote client_priors.json and freelancer_priors.json")


if __name__ == "__main__":
    main()
