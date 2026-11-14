from __future__ import annotations

from pathlib import Path
from typing import Iterable

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

MODEL_PATH = Path("artifacts/ticket_router_model.joblib")

_LABELS = [
    "queue_1",
    "queue_2",
    "queue_3",
    "queue_4",
    "queue_5",
    "queue_6",
    "queue_7",
    "queue_8",
    "queue_9",
    "queue_10",
    "queue_11",
    "queue_12",
    "queue_13",
    "queue_14",
]


def build_model() -> Pipeline:
    # TF-IDF + linear SVM is a strong baseline for ticket routing.
    return Pipeline(
        steps=[
            (
                "tfidf",
                TfidfVectorizer(
                    lowercase=True,
                    ngram_range=(1, 2),
                    min_df=2,
                    max_df=0.95,
                    strip_accents="unicode",
                ),
            ),
            ("clf", LinearSVC()),
        ]
    )


def save_model(model: Pipeline, path: Path = MODEL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)


def load_model(path: Path = MODEL_PATH) -> Pipeline:
    return joblib.load(path)


def predict(texts: str | Iterable[str], model: Pipeline | None = None):
    # Accept a single ticket or a batch of tickets.
    if model is None:
        model = load_model()

    if isinstance(texts, str):
        return model.predict([texts])[0]

    return model.predict(list(texts))


def validate_labels(labels: Iterable[str]) -> None:
    missing = set(_LABELS) - set(labels)
    if missing:
        raise ValueError(f"Missing expected queues: {sorted(missing)}")
