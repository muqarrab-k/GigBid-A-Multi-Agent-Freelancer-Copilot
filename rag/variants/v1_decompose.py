from rag.index.store import Filters
from rag.variants.base import EvidenceHit, Job, Variant, query_text
from rag.variants.fusion import rrf


def queries_for(job: Job) -> list[str]:
    """Whole post plus one query per analyst requirement."""
    if isinstance(job, str):
        return [job]
    reqs = [str(r).strip() for r in job.get("requirements") or [] if str(r).strip()]
    return [query_text(job), *reqs]


class V1Decompose:
    """One retrieval per requirement, merged with RRF."""

    name = "v1"

    def __init__(self, inner: Variant, rrf_k: int, depth: int) -> None:
        self.inner, self.rrf_k, self.depth = inner, rrf_k, depth

    def retrieve(self, job: Job, persona: str, k: int, filters: Filters | None = None) -> list[EvidenceHit]:
        lists = [self.inner.retrieve(q, persona, max(k, self.depth), filters) for q in queries_for(job)]
        first: dict[str, EvidenceHit] = {}
        for hits in lists:
            for hit in hits:
                first.setdefault(hit.evidence_id, hit)
        fused = rrf([[h.evidence_id for h in hits] for hits in lists], self.rrf_k)[:k]
        return [first[str(e)].model_copy(update={"score": round(s, 4)}) for e, s in fused]
