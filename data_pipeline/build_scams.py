import json
import math
from collections import Counter
from typing import Any

import pandas as pd
from pydantic import TypeAdapter

from data_pipeline.clean import clean_text, dup_groups, exact_key, near_key, normalise
from data_pipeline.common import PROCESSED_DIR, RAW_DIR
from data_pipeline.schema import ScamExample

LABELLED = "processed_labeled_dataset_without_encoding.xlsx"
TEMPLATE_RE = r"earn \d+\s?week"
MIN_FAKE_DOCS = 15
MIN_REAL_DOCS = 5
TOP_N = 40


def log(msg: str) -> None:
    print(f"  {msg}")


def load_examples() -> pd.DataFrame:
    df = pd.read_excel(RAW_DIR / "fake_jobs" / LABELLED, usecols=["text", "fraudulent"])
    log(f"fake_jobs labelled rows: {len(df):,} (unlabelled file skipped: no labels)")
    unlabelled = df["fraudulent"].isna()
    log(f"dropped rows with no fraudulent label: {unlabelled.sum():,}")
    df = df[~unlabelled].copy()
    df["text"] = df["text"].map(clean_text)
    no_text = df["text"].isna()
    log(f"dropped rows with no text: {no_text.sum():,}")
    df = df[~no_text]

    out = pd.DataFrame(
        {
            "text": df["text"],
            "label": df["fraudulent"].map({1.0: "fake", 0.0: "real"}),
            "source": "fake_jobs",
            "templated": df["text"].str.contains(TEMPLATE_RE, regex=True),
        }
    )
    TypeAdapter(list[ScamExample]).validate_python(out.to_dict(orient="records"))
    return out.reset_index(drop=True)


def terms(text: str) -> set[str]:
    words = normalise(text).split()
    return set(words) | {f"{a} {b}" for a, b in zip(words, words[1:], strict=False)}


def scam_signals(df: pd.DataFrame) -> dict[str, Any]:
    """Terms most over-represented in fake posts."""
    organic = df[~df["templated"]]
    # one post per repost group
    groups = dup_groups(
        [exact_key(t, None) for t in organic["text"]], [near_key(None, t) for t in organic["text"]]
    )
    organic = organic.assign(group=groups).drop_duplicates("group")
    counts: dict[str, Counter[str]] = {label: Counter() for label in ("fake", "real")}
    for text, label in zip(organic["text"], organic["label"], strict=True):
        counts[label].update(terms(text))
    n_fake = int((organic["label"] == "fake").sum())
    n_real = int((organic["label"] == "real").sum())

    scored = []
    for term, fake in counts["fake"].items():
        real = counts["real"][term]
        # skip one-company terms
        if fake < MIN_FAKE_DOCS or real < MIN_REAL_DOCS or any(c.isdigit() for c in term):
            continue
        log_odds = math.log((fake + 1) / (n_fake + 1)) - math.log((real + 1) / (n_real + 1))
        scored.append((log_odds, term, fake, real))
    scored.sort(reverse=True)

    fake_rows = df[df["label"] == "fake"]
    return {
        "source": "fake_jobs (labelled file)",
        "method": "smoothed log-odds of unigrams/bigrams, fake vs real; templated rows excluded,"
        " near-duplicate posts counted once, terms must also appear in real posts",
        "docs": {"fake": n_fake, "real": n_real},
        "templated_fake_share": round(float(fake_rows["templated"].mean()), 4),
        "template_pattern": TEMPLATE_RE,
        "signals": [
            {
                "term": term,
                "log_odds": round(score, 3),
                "fake_doc_rate": round(fake / n_fake, 4),
                "real_doc_rate": round(real / n_real, 4),
            }
            for score, term, fake, real in scored[:TOP_N]
        ],
    }


def main() -> pd.DataFrame:
    df = load_examples()
    df.to_parquet(PROCESSED_DIR / "scam_examples.parquet", index=False)
    signals = scam_signals(df)
    (PROCESSED_DIR / "scam_signals.json").write_text(json.dumps(signals, indent=2))
    fake = (df["label"] == "fake").sum()
    log(f"scam examples: {len(df):,} ({fake:,} fake, {df['templated'].sum():,} templated)")
    return df


if __name__ == "__main__":
    main()
