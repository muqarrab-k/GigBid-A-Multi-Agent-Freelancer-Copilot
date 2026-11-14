import json
import math
from pathlib import Path

import numpy as np
import pytest

from agent.config import ChunkingConfig
from evals.metrics import mrr, ndcg_at_k, percentile, recall_at_k
from rag.embeddings import CachedEmbedder, FakeEmbedder
from rag.index.store import Filters, MemoryStore
from rag.ingest.chunking import FixedChunker, get_chunker
from rag.ingest.documents import Document
from rag.ingest.indexer import index_documents, index_new_work
from rag.ingest.loaders import FolderLoader, PersonaLoader, persona_names
from rag.retriever import get_retriever
from rag.variants.base import query_text
from rag.variants.v0_naive import V0Naive

REQUIRED = ["evidence_id", "persona", "type", "source_path"]


def doc(eid: str, text: str, persona: str = "p", **kw: object) -> Document:
    return Document(evidence_id=eid, persona=persona, type="case_study", text=text, source_path=f"{eid}.md", **kw)


class CountingEmbedder(FakeEmbedder):
    def __init__(self) -> None:
        super().__init__(32)
        self.seen: list[str] = []

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        self.seen += texts
        return super().embed_documents(texts)


def test_persona_loader_metadata_complete() -> None:
    assert persona_names() == ["ai_ml", "data_analyst", "fullstack"]
    docs = PersonaLoader("ai_ml").load()
    manifest = [json.loads(x) for x in Path("data/personas/ai_ml/manifest.jsonl").read_text().splitlines()]
    assert len(docs) == len(manifest)
    for d in docs:
        assert all(getattr(d, f) for f in REQUIRED) and d.text.strip()
        assert d.persona == "ai_ml" and len(d.content_hash) == 64
        if d.type == "proposal":
            assert d.outcome in {"won", "replied", "ignored"}
        elif d.type != "cv":
            assert d.project and d.skills and d.date and d.client_industry
    cv = next(d for d in docs if d.type == "cv")
    assert "Noor Halden" in cv.text


def test_folder_loader_infers_metadata(tmp_path: Path) -> None:
    (tmp_path / "shop").mkdir()
    (tmp_path / "shop" / "README.md").write_text("# Shop\nBuilt with `FastAPI` and `Redis`.")
    (tmp_path / "shop" / "app.py").write_text("def main():\n    return 1\n")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "x.py").write_text("ignored")
    docs = {d.evidence_id: d for d in FolderLoader(tmp_path).load()}
    assert set(docs) == {"local:shop/README.md", "local:shop/app.py"}
    assert docs["local:shop/README.md"].type == "readme" and "FastAPI" in docs["local:shop/README.md"].skills
    assert docs["local:shop/app.py"].type == "code" and docs["local:shop/app.py"].skills == ["Python"]
    assert docs["local:shop/app.py"].project == "shop"


def test_chunker_is_deterministic_and_overlaps() -> None:
    text = "\n".join(f"word{i}" for i in range(450))
    chunker = FixedChunker(200, 40)
    first, second = chunker.split(doc("a", text)), chunker.split(doc("a", text))
    assert [c.text for c in first] == [c.text for c in second]
    assert [c.chunk_id for c in first] == ["a::0", "a::1", "a::2"]
    assert first[0].text.split()[-40:] == first[1].text.split()[:40]
    assert "\n" in first[0].text
    assert first[-1].text.split()[-1] == "word449"
    assert get_chunker(ChunkingConfig(size_words=50, overlap_words=10)).split(doc("b", "x " * 10))[0].text == "x " * 9 + "x"


def test_incremental_reindex_only_embeds_changes() -> None:
    store, embedder, chunker = MemoryStore(), CountingEmbedder(), FixedChunker(50, 10)
    docs = [doc("a", "alpha project with python"), doc("b", "beta dashboard in power bi"), doc("c", "gamma api")]
    first = index_documents(docs, "p", store, embedder, chunker)
    assert (first.added, first.chunks_embedded) == (3, 3)

    embedder.seen.clear()
    again = index_documents(docs, "p", store, embedder, chunker)
    assert again.unchanged == 3 and embedder.seen == []

    changed = [doc("a", "alpha project with python and celery"), docs[1]]
    third = index_documents(changed, "p", store, embedder, chunker)
    assert (third.updated, third.removed, third.unchanged) == (1, 1, 1)
    assert embedder.seen == ["alpha project with python and celery"]
    assert set(store.doc_hashes("p")) == {"a", "b"}

    upload = index_new_work([doc("d", "delta new work")], "p", store, embedder, chunker)
    assert upload.added == 1 and set(store.doc_hashes("p")) == {"a", "b", "d"}
    with pytest.raises(ValueError):
        index_documents([doc("x", "other", persona="q")], "p", store, embedder, chunker)


def test_embedding_cache_by_hash(tmp_path: Path) -> None:
    inner = CountingEmbedder()
    cached = CachedEmbedder(inner, tmp_path / "cache.sqlite")
    one = cached.embed_documents(["hello world", "second text"])
    two = cached.embed_documents(["second text", "hello world"])
    assert inner.seen == ["hello world", "second text"] or sorted(inner.seen) == ["hello world", "second text"]
    assert np.allclose(one[0], two[1]) and cached.stats["cached"] == 2


def test_v0_retrieves_best_evidence_per_item() -> None:
    store, embedder = MemoryStore(), FakeEmbedder(64)
    docs = [
        doc("cs1", "langchain retrieval assistant over contracts with pgvector", project="p1"),
        doc("cs2", "power bi sales dashboard with dax measures", project="p2"),
        doc("cs3", "langchain chatbot with openai tool calling " * 30, project="p3"),
        doc("other", "langchain retrieval assistant", persona="q"),
    ]
    for persona in ("p", "q"):
        index_documents([d for d in docs if d.persona == persona], persona, store, embedder, FixedChunker(20, 5))
    v0 = V0Naive(store, embedder)
    hits = v0.retrieve({"title": "LangChain retrieval assistant", "description": "contracts and pgvector"}, "p", 3)
    assert hits[0].evidence_id == "cs1"
    assert len({h.evidence_id for h in hits}) == len(hits) and all(h.evidence_id != "other" for h in hits)
    assert [h.evidence_id for h in v0.retrieve("power bi dax", "p", 1)] == ["cs2"]
    assert v0.retrieve("langchain", "p", 5, Filters(project="p2"))[0].project == "p2"
    assert get_retriever("v0", store=store, embedder=embedder).name == "v0"
    with pytest.raises(ValueError):
        get_retriever("v9", store=store, embedder=embedder)


def test_query_text_uses_title_description_skills() -> None:
    assert query_text({"title": "T", "description": "D", "skills": ["A", "B"]}) == "T\nD\nSkills: A, B"
    assert query_text("just text") == "just text"


def test_metrics_match_hand_computed_values() -> None:
    ranked = ["a", "x", "b", "y", "c"]
    relevant = {"a", "b", "z"}
    assert recall_at_k(ranked, relevant, 5) == pytest.approx(2 / 3)
    assert recall_at_k(ranked, relevant, 1) == pytest.approx(1 / 3)
    assert mrr(ranked, relevant) == 1.0
    assert mrr(["x", "y", "b"], relevant) == pytest.approx(1 / 3)
    assert mrr(["x"], relevant) == 0.0
    # dcg = 1/log2(2) + 1/log2(4) = 1.5; idcg = 1 + 1/log2(3) + 1/log2(4)
    idcg = 1 + 1 / math.log2(3) + 0.5
    assert ndcg_at_k(ranked, relevant, 10) == pytest.approx(1.5 / idcg)
    assert ndcg_at_k(["a", "b", "z"], relevant, 3) == pytest.approx(1.0)
    assert percentile([1, 2, 3, 4, 100], 50) == 3 and percentile([1, 2, 3, 4, 100], 95) == 100
