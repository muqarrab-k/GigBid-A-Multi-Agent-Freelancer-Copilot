import pytest

from rag.embeddings import FakeEmbedder
from rag.index.bm25 import BM25, tokenize
from rag.index.store import Filters, MemoryStore
from rag.ingest.chunking import FixedChunker
from rag.ingest.documents import Document
from rag.ingest.indexer import index_documents
from rag.retriever import get_retriever, load_presets
from rag.variants.base import EvidenceHit
from rag.variants.fusion import rrf
from rag.variants.type_filter import TypeFilter
from rag.variants.v0_naive import V0Naive
from rag.variants.v1_decompose import V1Decompose, queries_for
from rag.variants.v3_rerank import V3Rerank
from rag.variants.v8_corrective import V8Corrective


class FakeReranker:
    """Scores by keyword overlap with a fixed word."""

    model = "fake"

    def __init__(self, word: str = "dbt", hit: float = 0.9) -> None:
        self.word, self.hit, self.calls = word, hit, 0

    def score(self, query: str, texts: list[str]) -> list[float]:
        self.calls += 1
        return [self.hit if self.word in t.lower() else 0.01 for t in texts]


def doc(eid: str, text: str, kind: str = "case_study") -> Document:
    return Document(evidence_id=eid, persona="p", type=kind, text=text, source_path=f"{eid}.md")


@pytest.fixture
def setup() -> tuple[MemoryStore, FakeEmbedder]:
    store, embedder = MemoryStore(), FakeEmbedder(64)
    docs = [doc("cs1", "warehouse models built in dbt with snowflake"),
            doc("cs2", "celery workers for background jobs in django"),
            doc("cs3", "react dashboard with charts"),
            doc("pr1", "proposal: I would love to build your dbt warehouse", "proposal")]
    index_documents(docs, "p", store, embedder, FixedChunker(50, 5))
    return store, embedder


def test_rrf_math() -> None:
    fused = dict(rrf([["a", "b"], ["b", "c"]], k=60))
    assert fused["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert fused["a"] == pytest.approx(1 / 61) and fused["c"] == pytest.approx(1 / 62)
    assert [x for x, _ in rrf([["a", "b"], ["b", "c"]], k=60)][0] == "b"


def test_bm25_exact_token_match() -> None:
    docs = ["built dbt models on snowflake", "celery task queue with redis", "react front end"]
    bm25 = BM25(docs)
    assert max(range(3), key=lambda i: bm25.scores("dbt")[i]) == 0
    assert max(range(3), key=lambda i: bm25.scores("Celery")[i]) == 1
    assert bm25.scores("kubernetes") == [0.0, 0.0, 0.0]
    assert "node.js" in tokenize("Node.js and C++") and "c++" in tokenize("Node.js and C++")


def test_reranker_interface_with_fake(setup: tuple[MemoryStore, FakeEmbedder]) -> None:
    store, embedder = setup
    v3 = V3Rerank(V0Naive(store, embedder), FakeReranker("celery"), candidates=10)
    hits = v3.retrieve("background job queue", "p", 2)
    assert hits[0].evidence_id == "cs2" and hits[0].score == 0.9 and len(hits) == 2


def test_v8_refuses_when_nothing_passes(setup: tuple[MemoryStore, FakeEmbedder]) -> None:
    store, embedder = setup
    grader = FakeReranker("kubernetes")
    v8 = V8Corrective(V0Naive(store, embedder), grader, pass_score=0.5, min_passing=1)
    state = v8.run({"title": "Kubernetes operator", "skills": ["Kubernetes"]}, "p", 3)
    assert state["status"] == "no_evidence" and state["hits"] == [] and state["tries"] == 1
    assert grader.calls == 2


def test_v8_passes_without_rewrite(setup: tuple[MemoryStore, FakeEmbedder]) -> None:
    store, embedder = setup
    v8 = V8Corrective(V0Naive(store, embedder), FakeReranker("dbt"), pass_score=0.5, min_passing=1)
    state = v8.run("dbt warehouse", "p", 3)
    assert state["status"] == "ok" and state["hits"] and state["tries"] == 0


def test_type_filter_and_decompose(setup: tuple[MemoryStore, FakeEmbedder]) -> None:
    store, embedder = setup
    v = TypeFilter(V0Naive(store, embedder), ["case_study"])
    assert all(h.type == "case_study" for h in v.retrieve("dbt warehouse", "p", 5))
    assert v.retrieve("dbt", "p", 5, Filters(types=["proposal"]))[0].evidence_id == "pr1"
    job = {"title": "T", "requirements": ["dbt models", "celery workers"]}
    assert queries_for(job)[1:] == ["dbt models", "celery workers"] and queries_for("x") == ["x"]
    ids = {h.evidence_id for h in V1Decompose(v.inner, 60, 5).retrieve(job, "p", 4)}
    assert {"cs1", "cs2"} <= ids


def test_factory_builds_every_variant(setup: tuple[MemoryStore, FakeEmbedder]) -> None:
    store, embedder = setup
    for name in load_presets()["presets"]:
        v = get_retriever(name, store=store, embedder=embedder, reranker=FakeReranker())
        assert v.name == name
        hits = v.retrieve({"title": "dbt warehouse", "requirements": ["dbt"]}, "p", 3)
        assert all(isinstance(h, EvidenceHit) for h in hits)
    assert get_retriever("filter+hybrid", store=store, embedder=embedder).name == "filter+hybrid"
    with pytest.raises(ValueError):
        get_retriever("v9", store=store, embedder=embedder)
