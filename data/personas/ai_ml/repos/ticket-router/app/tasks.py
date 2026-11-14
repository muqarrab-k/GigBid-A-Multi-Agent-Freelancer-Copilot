from celery import Celery
from pathlib import Path
from tempfile import NamedTemporaryFile
import os
import shutil

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from app.db import get_session, fetch_new_labeled_tickets

celery_app = Celery(
    "ticket_router",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/0"),
)

MODEL_PATH = Path(os.getenv("MODEL_PATH", "models/routing_model.joblib"))


def build_pipeline() -> Pipeline:
    # Simple text classifier for ticket routing
    return Pipeline(
        [
            ("tfidf", TfidfVectorizer(stop_words="english", ngram_range=(1, 2))),
            ("clf", LogisticRegression(max_iter=1000)),
        ]
    )


def load_existing_model() -> Pipeline | None:
    if MODEL_PATH.exists():
        return joblib.load(MODEL_PATH)
    return None


@celery_app.task(name="app.tasks.retrain_router_model")
def retrain_router_model() -> dict:
    session = get_session()
    try:
        rows = fetch_new_labeled_tickets(session)
        if not rows:
            return {"status": "skipped", "reason": "no new labeled tickets"}

        texts = [row["text"] for row in rows]
        labels = [row["queue"] for row in rows]

        model = build_pipeline()
        model.fit(texts, labels)

        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("wb", delete=False, dir=str(MODEL_PATH.parent)) as tmp:
            joblib.dump(model, tmp.name)
            temp_path = Path(tmp.name)

        shutil.move(str(temp_path), MODEL_PATH)
        return {"status": "ok", "trained_on": len(rows), "model_path": str(MODEL_PATH)}
    finally:
        session.close()
