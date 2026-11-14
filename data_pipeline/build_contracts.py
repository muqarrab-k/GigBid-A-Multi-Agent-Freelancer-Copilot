import pandas as pd
from pydantic import TypeAdapter

from agent.config import get_config
from data_pipeline.clean import clean_text, stable_id
from data_pipeline.common import PROCESSED_DIR, RAW_DIR
from data_pipeline.persona import persona_tags
from data_pipeline.schema import ContractRecord


def log(msg: str) -> None:
    print(f"  {msg}")


def parse_dates(values: pd.Series) -> pd.Series:
    cfg = get_config().data
    dates = pd.to_datetime(values, errors="coerce", format="ISO8601")
    low, high = pd.Timestamp(cfg.contract_date_min), pd.Timestamp(cfg.contract_date_max)
    bad = dates.notna() & ((dates < low) | (dates > high))
    log(f"{values.name}: {bad.sum():,} dates outside {low.date()}..{high.date()} set to null")
    return dates.where(~bad)


def build() -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "contracts_1_3m" / "contracts.csv")
    log(f"contracts raw rows: {len(df):,}")
    df["title"] = df["job_title"].map(clean_text)
    no_title = df["title"].isna()
    log(f"dropped contracts with no title: {no_title.sum():,}")
    df = df[~no_title].reset_index(drop=True)

    start, end = parse_dates(df["start_date"]), parse_dates(df["end_date"])
    days = (end - start).dt.total_seconds() / 86400
    negative = days < 0
    log(f"negative durations set to null: {negative.sum():,}")

    out = pd.DataFrame(
        {
            "contract_id": [
                stable_id(j, f, s)
                for j, f, s in zip(df["job_id"], df["freelancer_id"], df["start_date"], strict=True)
            ],
            "title": df["title"],
            "contract_type": df["hourly_rate"].notna().map({True: "hourly", False: "fixed"}),
            "status": df["end_date"].notna().map({True: "ended", False: "ongoing"}),
            "start_date": start,
            "end_date": end,
            "duration_days": days.where(~negative),
            "total_hours": df["total_hours"],
            "total_paid": df["total_paid"],
            "hourly_rate": df["hourly_rate"],
            "freelancer_id": df["freelancer_id"],
            "persona_tags": [persona_tags(t, [], None) for t in df["title"]],
        }
    )
    return out


def validate(df: pd.DataFrame) -> None:
    records = df.astype(object).where(df.notna(), None).to_dict(orient="records")
    TypeAdapter(list[ContractRecord]).validate_python(records)


def main() -> pd.DataFrame:
    df = build()
    validate(df)
    df.to_parquet(PROCESSED_DIR / "contracts.parquet", index=False)
    log(f"contracts kept: {len(df):,} ({(df['contract_type'] == 'hourly').mean():.1%} hourly)")
    return df


if __name__ == "__main__":
    main()
