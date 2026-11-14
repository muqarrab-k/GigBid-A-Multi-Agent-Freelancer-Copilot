from celery import Celery
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient, models

from app.config import settings

celery_app = Celery(
    "resume_match",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

MODEL_NAME = getattr(settings, "embedding_model_name", "sentence-transformers/all-MiniLM-L6-v2")
COLLECTION_NAME = getattr(settings, "qdrant_collection_name", "resumes")

_model = None
_qdrant = None


def get_model() -> SentenceTransformer:
    global _model
    if _model is None:
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def get_qdrant() -> QdrantClient:
    global _qdrant
    if _qdrant is None:
        _qdrant = QdrantClient(
            url=settings.qdrant_url,
            api_key=getattr(settings, "qdrant_api_key", None),
            timeout=30,
        )
    return _qdrant


def build_resume_text(resume: dict) -> str:
    parts = [
        resume.get("headline", ""),
        resume.get("summary", ""),
        " ".join(resume.get("skills", []) or []),
        " ".join(resume.get("experience", []) or []),
    ]
    return "\n".join(p for p in parts if p).strip()


@celery_app.task(name="embed_worker.embed_resume")
def embed_resume(resume_id: str, resume: dict) -> dict:
    text = build_resume_text(resume)
    if not text:
        return {"resume_id": resume_id, "status": "skipped"}

    vector = get_model().encode(text, normalize_embeddings=True).tolist()
    payload = {
        "resume_id": resume_id,
        "name": resume.get("name"),
        "updated_at": resume.get("updated_at"),
    }

    get_qdrant().upsert(
        collection_name=COLLECTION_NAME,
        points=[
            models.PointStruct(
                id=resume_id,
                vector=vector,
                payload=payload,
            )
        ],
    )
    return {"resume_id": resume_id, "status": "upserted"}
