from collections import Counter

import pandas as pd
from pydantic import TypeAdapter

from agent.config import get_config
from data_pipeline.clean import (
    clean_text,
    detect_currency,
    dup_groups,
    exact_key,
    near_key,
    normalise,
    parse_money,
    parse_range,
    stable_id,
)
from data_pipeline.common import PROCESSED_DIR, RAW_DIR
from data_pipeline.persona import persona_tags
from data_pipeline.schema import MarketJob

KEY_RE = r"(?:~|%7E)(01[0-9a-fA-F]{16})"
TAG_COLS = [f"Category_{i}" for i in range(1, 10)]
MIN_TAG_COUNT = 20


def log(msg: str) -> None:
    print(f"  {msg}")


def job_key(links: pd.Series) -> pd.Series:
    return links.str.extract(KEY_RE)[0].str.lower()


def load_2024() -> pd.DataFrame:
    """50k (with descriptions) plus 200k (titles only)."""
    with_desc = pd.read_csv(RAW_DIR / "jobs_2024_50k" / "upwork-jobs.csv")
    with_desc["source"] = "jobs_2024_50k"
    parts = [with_desc]
    for path in sorted((RAW_DIR / "jobs_200k").glob("*.csv")):
        part = pd.read_csv(path)
        part["source"] = "jobs_200k"
        part["description"] = None
        parts.append(part)
    df = pd.concat(parts, ignore_index=True)
    log(f"2024 raw rows: {len(df):,}")

    df["key"] = job_key(df["link"])
    df["has_desc"] = df["description"].notna()
    df = df.sort_values(["has_desc"], ascending=False, kind="stable")
    before = len(df)
    df = df[df["key"].isna() | ~df["key"].duplicated()]
    log(f"2024 repeat scrapes of same job URL collapsed: {before - len(df):,}")

    budget = df["budget"]
    hourly = df["is_hourly"].map({True: True, False: False, "True": True, "False": False})
    # infer missing flag
    hourly = hourly.where(hourly.notna(), df["hourly_low"].notna() | df["hourly_high"].notna())
    hourly = hourly.where(hourly | budget.notna() | df["hourly_low"].notna(), None)
    log(f"2024 is_hourly missing, inferred from price fields: {df['is_hourly'].isna().sum():,}")

    return pd.DataFrame(
        {
            "key": df["key"],
            "source": df["source"],
            "title": df["title"],
            "description": df["description"],
            "tags": [[] for _ in range(len(df))],
            "category": None,
            "budget_type": hourly.map({True: "hourly", False: "fixed"}),
            "budget": budget,
            "hourly_min": df["hourly_low"],
            "hourly_max": df["hourly_high"],
            "currency": "USD",
            "client_country": df["country"],
            "posted_at": pd.to_datetime(df["published_date"], utc=True, format="ISO8601"),
            "experience_level": None,
            "connects": None,
        }
    )


def load_2023() -> pd.DataFrame:
    df = pd.read_csv(RAW_DIR / "jobs_2023_60k" / "Final_Upwork_Dataset.csv", low_memory=False)
    log(f"2023 raw rows: {len(df):,}")
    df["key"] = job_key(df["Job_URL"])
    before = len(df)
    df = df[df["key"].isna() | ~df["key"].duplicated()]
    log(f"2023 same job URL under several search keywords collapsed: {before - len(df):,}")

    kind = df["Payment_type"].map({"Fixed-price": "fixed", "Hourly": "hourly"})
    rates = df["Hourly_Rate"].map(parse_range)
    tags = df[TAG_COLS].apply(lambda row: [str(t).strip() for t in row.dropna()], axis=1)
    return pd.DataFrame(
        {
            "key": df["key"],
            "source": "jobs_2023_60k",
            "title": df["Job Title"],
            "description": df["Description"],
            "tags": tags,
            "category": df["Search_Keyword"].str.replace("_", " "),
            "budget_type": kind,
            "budget": df["Job_Cost"].map(parse_money).where(kind == "fixed"),
            "hourly_min": rates.map(lambda r: r[0]).where(kind == "hourly"),
            "hourly_max": rates.map(lambda r: r[1]).where(kind == "hourly"),
            "currency": df["Job_Cost"].fillna(df["Hourly_Rate"]).map(detect_currency),
            "client_country": df["Client_Country"],
            "posted_at": pd.NaT,
            "experience_level": df["EX_level_demand"],
            "connects": df["New_Connects_Num"],
        }
    )


def skill_vocab(tag_lists: pd.Series) -> dict[str, str]:
    """Frequent real tags, normalised -> display."""
    counts = Counter(tag for tags in tag_lists for tag in tags)
    vocab: dict[str, str] = {}
    for tag, count in counts.items():
        norm = normalise(tag)
        if count >= MIN_TAG_COUNT and len(norm) > 1:
            vocab.setdefault(norm, tag)
    return vocab


def match_skills(text: str, vocab: dict[str, str], max_len: int) -> list[str]:
    words = normalise(text).split()
    found = []
    for n in range(max_len, 0, -1):
        for i in range(len(words) - n + 1):
            tag = vocab.get(" ".join(words[i : i + n]))
            if tag and tag not in found:
                found.append(tag)
    return found


def clip_prices(df: pd.DataFrame) -> pd.DataFrame:
    cfg = get_config().data
    for col, cap in (
        ("budget", cfg.max_fixed_budget),
        ("hourly_min", cfg.max_hourly_rate),
        ("hourly_max", cfg.max_hourly_rate),
    ):
        bad = (df[col] <= 0) | (df[col] > cap)
        log(f"{col}: {bad.sum():,} values <= 0 or > {cap:,.0f} set to null")
        df.loc[bad, col] = None
    swapped = df["hourly_max"] < df["hourly_min"]
    log(f"hourly ranges swapped (max < min): {swapped.sum():,}")
    df.loc[swapped, ["hourly_min", "hourly_max"]] = df.loc[
        swapped, ["hourly_max", "hourly_min"]
    ].to_numpy()
    return df


def add_connects(df: pd.DataFrame) -> pd.DataFrame:
    rule = get_config().bidding_rules.connects_rule
    real = df["connects"].notna()
    by_rule = [
        rule.connects_for(kind, budget if budget == budget else None)
        for kind, budget in zip(df["budget_type"], df["budget"], strict=True)
    ]
    df["connects_cost"] = df["connects"].where(real, pd.Series(by_rule, index=df.index))
    df["connects_source"] = real.map({True: "real", False: "rule"})

    # rule vs real check
    check = df[real & (df["budget_type"] == "fixed")]
    agree = (pd.Series(by_rule, index=df.index)[check.index] == check["connects"]).mean()
    log(f"connects: {real.sum():,} real, {(~real).sum():,} from config rule")
    log(f"connects rule matches real value on {agree:.1%} of real fixed jobs")
    return df


def build(frames: list[pd.DataFrame]) -> pd.DataFrame:
    df = pd.concat(frames, ignore_index=True)
    df["title"] = df["title"].map(clean_text)
    df["description"] = df["description"].map(clean_text)
    no_title = df["title"].isna()
    log(f"dropped rows with no title: {no_title.sum():,}")
    df = df[~no_title].reset_index(drop=True)

    df = clip_prices(df)
    df["budget_type"] = df["budget_type"].where(df["budget_type"].notna(), None)

    vocab = skill_vocab(df["tags"])
    max_len = max(len(k.split()) for k in vocab)
    log(f"skill vocabulary from real 2023 tags: {len(vocab):,} skills")
    has_tags = df["tags"].map(bool)
    text = df["title"] + " " + df["description"].fillna("")
    df["skills"] = df["tags"].where(has_tags, text.map(lambda t: match_skills(t, vocab, max_len)))
    df["skills_source"] = has_tags.map({True: "tags", False: "keywords"})
    df.loc[~df["skills"].map(bool), "skills_source"] = None

    # NaN to None
    desc = [d if isinstance(d, str) else None for d in df["description"]]
    df["persona_tags"] = [
        persona_tags(t, s, d) for t, s, d in zip(df["title"], df["skills"], desc, strict=True)
    ]
    df = add_connects(df)

    ids = [
        stable_id(key) if isinstance(key, str) else stable_id(src, t, d)
        for key, src, t, d in zip(df["key"], df["source"], df["title"], desc, strict=True)
    ]
    df["job_id"] = ids
    df["desc"] = desc
    before = len(df)
    df = df.drop_duplicates("job_id").reset_index(drop=True)
    log(f"dropped repeated job_id (no URL key, same text): {before - len(df):,}")

    # title-only, unpriced rows stay alone
    priced = df[["budget", "hourly_min", "hourly_max"]].notna().any(axis=1)
    exact = [
        exact_key(t, d, c, k, b, lo, hi) if isinstance(d, str) or p else jid
        for t, d, c, k, b, lo, hi, p, jid in zip(
            df["title"], df["desc"], df["client_country"], df["budget_type"],
            df["budget"], df["hourly_min"], df["hourly_max"], priced, df["job_id"], strict=True,
        )
    ]
    near = [near_key(t, d) for t, d in zip(df["title"], df["desc"], strict=True)]
    df["dup_group"] = dup_groups(exact, near)

    df["budget_min"] = df["budget"]
    df["budget_max"] = df["budget"]
    return df


def validate(df: pd.DataFrame) -> pd.DataFrame:
    fields = list(MarketJob.model_fields)
    records = df[fields].astype(object).where(df[fields].notna(), None).to_dict(orient="records")
    jobs = TypeAdapter(list[MarketJob]).validate_python(records)
    out = pd.DataFrame([j.model_dump() for j in jobs])
    out["posted_at"] = pd.to_datetime(out["posted_at"], utc=True)
    return out


def main() -> pd.DataFrame:
    df = build([load_2024(), load_2023()])
    jobs = validate(df)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    jobs.to_parquet(PROCESSED_DIR / "jobs.parquet", index=False)
    groups = jobs["dup_group"].nunique()
    log(f"jobs kept: {len(jobs):,}, dup groups: {groups:,}, duplicate rows: {len(jobs) - groups:,}")
    return jobs


if __name__ == "__main__":
    main()
