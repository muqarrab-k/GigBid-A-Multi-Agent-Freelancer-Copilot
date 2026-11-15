from rag.embeddings import Embedder
from rag.index.bm25 import BM25
from rag.index.store import Filters, VectorStore
from rag.ingest.documents import Chunk
from rag.variants.base import EvidenceHit, Job, best_per_evidence, query_text
from rag.variants.fusion import rrf


class V2Hybrid:
    """BM25 plus dense chunk rankings, merged with RRF."""

    name = "v2"

    def __init__(self, store: VectorStore, embedder: Embedder, pool: int, rrf_k: int) -> None:
        self.store, self.embedder, self.pool, self.rrf_k = store, embedder, pool, rrf_k
        self.indexes: dict[str, tuple[list[Chunk], BM25]] = {}

    def index(self, persona: str) -> tuple[list[Chunk], BM25]:
        if persona not in self.indexes:
            chunks = self.store.chunks(persona)
            self.indexes[persona] = (chunks, BM25([c.text for c in chunks]))
        return self.indexes[persona]

    def sparse(self, text: str, persona: str, filters: Filters | None) -> list[Chunk]:
        chunks, bm25 = self.index(persona)
        scored = [(c, s) for c, s in zip(chunks, bm25.scores(text), strict=True)
                  if s > 0 and (filters is None or filters.accepts(c))]
        return [c for c, _ in sorted(scored, key=lambda x: (-x[1], x[0].chunk_id))[: self.pool]]

    def retrieve(self, job: Job, persona: str, k: int, filters: Filters | None = None) -> list[EvidenceHit]:
        text = query_text(job)
        found = self.store.search(self.embedder.embed_query(text), persona, self.pool, filters)
        dense = [c for c, _ in found]
        sparse = self.sparse(text, persona, filters)
        by_id = {c.chunk_id: c for c in dense + sparse}
        fused = rrf([[c.chunk_id for c in dense], [c.chunk_id for c in sparse]], self.rrf_k)
        hits = best_per_evidence([(by_id[str(i)], s) for i, s in fused], k)
        # rank by rrf, but report cosine: fit thresholds are on that scale
        cosine: dict[str, float] = {}
        for chunk, score in found:
            cosine[chunk.evidence_id] = max(score, cosine.get(chunk.evidence_id, 0.0))
        return [h.model_copy(update={"score": round(cosine.get(h.evidence_id, 0.0), 4)}) for h in hits]
