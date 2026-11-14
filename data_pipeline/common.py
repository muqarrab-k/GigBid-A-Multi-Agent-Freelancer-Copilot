from pathlib import Path
from typing import Literal

import pandas as pd
import yaml
from pydantic import BaseModel

from agent.config import get_config

PATHS = get_config().paths
RAW_DIR = PATHS.raw_dir
PROCESSED_DIR = PATHS.processed_dir
SEED_DIR = PATHS.seed_dir
SOURCES_PATH = Path(__file__).with_name("sources.yaml")
TABLE_SUFFIXES = (".csv", ".xlsx", ".parquet")


class Source(BaseModel):
    name: str
    slug: str
    kind: Literal["jobs", "contracts", "freelancers", "scams"]
    origin: Literal["real", "synthetic"]

    @property
    def folder(self) -> Path:
        return RAW_DIR / self.name

    @property
    def url(self) -> str:
        return f"https://www.kaggle.com/datasets/{self.slug}"


def load_sources() -> list[Source]:
    raw = yaml.safe_load(SOURCES_PATH.read_text())
    return [Source(name=name, **info) for name, info in raw.items()]


def table_files(source: Source) -> list[Path]:
    """Data tables in a source folder."""
    if not source.folder.is_dir():
        return []
    files = [p for p in source.folder.rglob("*") if p.suffix.lower() in TABLE_SUFFIXES]
    return sorted(files)


def describe(values: pd.Series) -> dict[str, float | int]:
    """Count and p10-p90 of non-null values."""
    values = values.dropna()
    out: dict[str, float | int] = {"count": int(len(values))}
    if values.empty:
        return out
    for q in (10, 25, 50, 75, 90):
        out[f"p{q}"] = round(float(values.quantile(q / 100)), 2)
    return out


def shares(values: pd.Series, top: int | None = None) -> dict[str, float]:
    counts = values.fillna("missing").astype(str).value_counts(normalize=True)
    if top:
        counts = counts.head(top)
    return {k: round(float(v), 4) for k, v in counts.items()}
