from typing import Any

import yaml

from agent.config import ROOT, RagConfig, get_config
from rag.embeddings import Embedder, get_embedder
from rag.index.pgvector import PgVectorStore
from rag.index.store import MemoryStore, VectorStore
from rag.variants.base import Variant
from rag.variants.type_filter import TypeFilter
from rag.variants.v0_naive import V0Naive
from rag.variants.v1_decompose import V1Decompose
from rag.variants.v2_hybrid import V2Hybrid
from rag.variants.v3_rerank import CrossEncoderReranker, Reranker, V3Rerank
from rag.variants.v8_corrective import V8Corrective

PRESETS = ROOT / "rag" / "variants" / "presets.yaml"
PARTS = {"filter", "decompose", "hybrid", "rerank", "corrective"}


def load_presets() -> dict[str, Any]:
    return yaml.safe_load(PRESETS.read_text())


def build_store(cfg: RagConfig, embedder: Embedder, backend: str | None = None) -> VectorStore:
    if (backend or cfg.store.backend) == "memory":
        return MemoryStore()
    return PgVectorStore(cfg.store.dsn, cfg.store.schema_name, embedder.model, embedder.dim)


def parts_of(name: str, presets: dict[str, Any]) -> set[str]:
    """Preset name or a raw 'filter+hybrid' spec."""
    spec = presets["presets"].get(name, name if name not in ("", None) else "")
    parts = {p for p in str(spec).split("+") if p}
    if name not in presets["presets"] and (not parts or parts - PARTS):
        raise ValueError(f"unknown rag variant {name!r}, have {sorted(presets['presets'])}")
    return parts


def build_variant(name: str, store: VectorStore, embedder: Embedder, cfg: RagConfig,
                  reranker: Reranker | None = None) -> Variant:
    p = load_presets()
    parts = parts_of(name, p)
    v: Any = (V2Hybrid(store, embedder, p["hybrid"]["pool"], p["rrf_k"]) if "hybrid" in parts
              else V0Naive(store, embedder, cfg.candidate_multiplier))
    if "decompose" in parts:
        v = V1Decompose(v, p["rrf_k"], p["decompose"]["depth"])
    if parts & {"rerank", "corrective"} and reranker is None:
        r = p["rerank"]
        reranker = CrossEncoderReranker([r["model"] or cfg.reranker.model, r["fallback"]], r["max_length"])
    if "rerank" in parts:
        v = V3Rerank(v, reranker, p["rerank"]["candidates"])  # type: ignore[arg-type]
    if "corrective" in parts:
        c = p["corrective"]
        v = V8Corrective(v, reranker, c["pass_score"], c["min_passing"])  # type: ignore[arg-type]
    if "filter" in parts:
        v = TypeFilter(v, p["filter"]["types"])
    v.name = name
    return v  # type: ignore[no-any-return]


def get_retriever(variant: str | None = None, store: VectorStore | None = None,
                  embedder: Embedder | None = None, reranker: Reranker | None = None) -> Variant:
    """Retrieval variant chosen by config rag.variant."""
    cfg = get_config().rag
    name = variant or cfg.variant
    parts_of(name, load_presets())
    embedder = embedder or get_embedder(cfg.embeddings)
    store = store or build_store(cfg, embedder)
    return build_variant(name, store, embedder, cfg, reranker)
