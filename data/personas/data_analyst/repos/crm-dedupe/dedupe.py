from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd
from rapidfuzz import fuzz


@dataclass(frozen=True)
class Match:
    left_id: str
    right_id: str
    score: float


def email_domain(email: str | None) -> str:
    if not email or "@" not in str(email):
        return ""
    return str(email).strip().lower().split("@", 1)[1]


def normalize_name(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(str(value).strip().lower().split())


def block_by_domain(df: pd.DataFrame, email_col: str = "email") -> dict[str, pd.DataFrame]:
    # Group candidate records by email domain.
    domains = df[email_col].map(email_domain)
    return {domain: group.copy() for domain, group in df.groupby(domains) if domain}


def fuzzy_name_score(a: str | None, b: str | None) -> float:
    left = normalize_name(a)
    right = normalize_name(b)
    if not left or not right:
        return 0.0
    return float(fuzz.token_sort_ratio(left, right))


def find_matches(
    df: pd.DataFrame,
    id_col: str = "id",
    name_col: str = "name",
    email_col: str = "email",
    threshold: float = 90.0,
) -> list[Match]:
    matches: list[Match] = []
    for _, block in block_by_domain(df, email_col=email_col).items():
        rows = block.reset_index(drop=True)
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                score = fuzzy_name_score(rows.at[i, name_col], rows.at[j, name_col])
                if score >= threshold:
                    matches.append(
                        Match(
                            left_id=str(rows.at[i, id_col]),
                            right_id=str(rows.at[j, id_col]),
                            score=score,
                        )
                    )
    return matches


def matches_to_frame(matches: Iterable[Match]) -> pd.DataFrame:
    # Handy for reviewing the dedupe pass before writing back to Airtable.
    return pd.DataFrame([m.__dict__ for m in matches], columns=["left_id", "right_id", "score"])
