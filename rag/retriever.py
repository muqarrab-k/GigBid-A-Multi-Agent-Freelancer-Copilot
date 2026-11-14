from agent.config import RagConfig, get_config
from rag.embeddings import Embedder, get_embedder
from rag.index.pgvector import PgVectorStore
from rag.index.store import MemoryStore, VectorStore
from rag.variants.base import Variant
from rag.variants.v0_naive import V0Naive

VARIANTS = {"v0": V0Naive}


def build_store(cfg: RagConfig, embedder: Embedder, backend: str | None = None) -> VectorStore:
    if (backend or cfg.store.backend) == "memory":
        return MemoryStore()
    return PgVectorStore(cfg.store.dsn, cfg.store.schema_name, embedder.model, embedder.dim)


def get_retriever(variant: str | None = None, store: VectorStore | None = None,
                  embedder: Embedder | None = None) -> Variant:
    """Retrieval variant chosen by config rag.variant."""
    cfg = get_config().rag
    name = variant or cfg.variant
    if name not in VARIANTS:
        raise ValueError(f"unknown rag variant {name!r}, have {sorted(VARIANTS)}")
    embedder = embedder or get_embedder(cfg.embeddings)
    store = store or build_store(cfg, embedder)
    return VARIANTS[name](store, embedder, cfg.candidate_multiplier)
