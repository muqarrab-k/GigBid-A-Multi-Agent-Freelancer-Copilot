from rag.embeddings import Embedder
from rag.index.store import Filters, VectorStore
from rag.variants.base import EvidenceHit, Job, best_per_evidence, query_text


class V0Naive:
    """Baseline: fixed chunks, whole job post as the query, top-k cosine."""

    name = "v0"

    def __init__(self, store: VectorStore, embedder: Embedder, candidate_multiplier: int = 6) -> None:
        self.store, self.embedder, self.multiplier = store, embedder, candidate_multiplier

    def retrieve(self, job: Job, persona: str, k: int, filters: Filters | None = None) -> list[EvidenceHit]:
        vector = self.embedder.embed_query(query_text(job))
        scored = self.store.search(vector, persona, k * self.multiplier, filters)
        return best_per_evidence(scored, k)
