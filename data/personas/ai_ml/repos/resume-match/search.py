from typing import Any, Dict, List, Optional

from qdrant_client import QdrantClient
from qdrant_client.http import models as rest


client = QdrantClient(host="localhost", port=6333)

DEFAULT_LIMIT = 25
COLLECTION_NAME = "resumes"


def build_job_filter(
    min_years_experience: Optional[int] = None,
    location: Optional[str] = None,
    remote_only: Optional[bool] = None,
) -> Optional[rest.Filter]:
    must: List[Any] = []

    if min_years_experience is not None:
        must.append(
            rest.FieldCondition(
                key="years_experience",
                range=rest.Range(gte=min_years_experience),
            )
        )

    if location:
        must.append(
            rest.FieldCondition(
                key="location",
                match=rest.MatchValue(value=location),
            )
        )

    if remote_only is True:
        must.append(
            rest.FieldCondition(
                key="remote",
                match=rest.MatchValue(value=True),
            )
        )

    if not must:
        return None

    return rest.Filter(must=must)


def search_resumes(
    query_vector: List[float],
    limit: int = DEFAULT_LIMIT,
    min_years_experience: Optional[int] = None,
    location: Optional[str] = None,
    remote_only: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    # Qdrant vector search with simple recruiter filters
    query_filter = build_job_filter(
        min_years_experience=min_years_experience,
        location=location,
        remote_only=remote_only,
    )

    hits = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=query_vector,
        query_filter=query_filter,
        limit=limit,
        with_payload=True,
    )

    results: List[Dict[str, Any]] = []
    for hit in hits:
        payload = hit.payload or {}
        results.append(
            {
                "id": hit.id,
                "score": hit.score,
                "name": payload.get("name"),
                "headline": payload.get("headline"),
                "location": payload.get("location"),
                "years_experience": payload.get("years_experience"),
            }
        )

    return results
