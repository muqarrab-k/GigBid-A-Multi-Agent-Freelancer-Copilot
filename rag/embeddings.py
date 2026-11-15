import hashlib
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Protocol

import httpx
import numpy as np

from agent.config import EmbedderSpec, EmbeddingsConfig

log = logging.getLogger(__name__)


class Embedder(Protocol):
    model: str
    dim: int

    def embed_documents(self, texts: list[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...


def normalize(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    return (vectors / np.where(norms == 0, 1, norms)).astype(np.float32)


class SentenceTransformerEmbedder:
    def __init__(self, spec: EmbedderSpec) -> None:
        from sentence_transformers import SentenceTransformer

        self.spec, self.model, self.dim = spec, spec.model, spec.dim
        self.st = SentenceTransformer(spec.model, trust_remote_code=spec.trust_remote_code, device="cpu")

    def encode(self, texts: list[str]) -> np.ndarray:
        out: Any = self.st.encode(texts, batch_size=self.spec.batch_size, normalize_embeddings=True,
                                  show_progress_bar=False)
        return np.asarray(out, dtype=np.float32)

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self.encode([self.spec.document_prefix + t for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self.encode([self.spec.query_prefix + text])[0]


class OllamaEmbedder:
    def __init__(self, spec: EmbedderSpec) -> None:
        self.spec, self.model, self.dim = spec, spec.model, spec.dim
        self.client = httpx.Client(base_url=spec.base_url or "http://localhost:11434", timeout=120)

    def encode(self, texts: list[str]) -> np.ndarray:
        out = []
        for i in range(0, len(texts), self.spec.batch_size):
            resp = self.client.post("/api/embed", json={"model": self.model, "input": texts[i : i + self.spec.batch_size]})
            resp.raise_for_status()
            out.extend(resp.json()["embeddings"])
        return normalize(np.array(out, dtype=np.float32))

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self.encode([self.spec.document_prefix + t for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self.encode([self.spec.query_prefix + text])[0]


class NomicApiEmbedder:
    """nomic-embed-text over the Nomic API; task_type adds the search prefixes server side."""

    def __init__(self, spec: EmbedderSpec) -> None:
        key = os.getenv(spec.api_key_env or "")
        if not key:
            raise RuntimeError(f"{spec.api_key_env} is not set")
        self.spec, self.model, self.dim = spec, spec.model, spec.dim
        self.client = httpx.Client(base_url=spec.base_url or "https://api-atlas.nomic.ai", timeout=60,
                                   headers={"Authorization": f"Bearer {key}"})

    def encode(self, texts: list[str], task: str) -> np.ndarray:
        out = []
        for i in range(0, len(texts), self.spec.batch_size):
            resp = self.client.post("/v1/embedding/text", json={
                "model": self.model.split("/")[-1], "texts": texts[i : i + self.spec.batch_size],
                "task_type": task, "dimensionality": self.dim})
            resp.raise_for_status()
            out.extend(resp.json()["embeddings"])
        return normalize(np.array(out, dtype=np.float32))

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return self.encode(texts, "search_document") if texts else np.zeros((0, self.dim), np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self.encode([text], "search_query")[0]


class FakeEmbedder:
    """Deterministic hashed bag of words, for tests only."""

    def __init__(self, dim: int = 64) -> None:
        self.model, self.dim = f"fake-{dim}", dim

    def vector(self, text: str) -> np.ndarray:
        out = np.zeros(self.dim, dtype=np.float32)
        for word in text.lower().split():
            bucket = int(hashlib.md5(word.strip(".,:;()[]").encode()).hexdigest(), 16) % self.dim
            out[bucket] += 1
        return out

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        return normalize(np.stack([self.vector(t) for t in texts])) if texts else np.zeros((0, self.dim), np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed_documents([text])[0]


class CachedEmbedder:
    """Wraps an embedder with an sqlite cache keyed by model and text hash."""

    def __init__(self, inner: Embedder, path: Path) -> None:
        self.inner, self.model, self.dim = inner, inner.model, inner.dim
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.execute("CREATE TABLE IF NOT EXISTS vectors (model TEXT, hash TEXT, vec BLOB, PRIMARY KEY (model, hash))")
        self.stats = {"cached": 0, "embedded": 0, "seconds": 0.0}

    def embed_documents(self, texts: list[str]) -> np.ndarray:
        keys = [hashlib.sha256(t.encode()).hexdigest() for t in texts]
        found: dict[str, np.ndarray] = {}
        for i in range(0, len(keys), 500):
            batch = keys[i : i + 500]
            marks = ",".join("?" * len(batch))
            rows = self.db.execute(f"SELECT hash, vec FROM vectors WHERE model = ? AND hash IN ({marks})",
                                   (self.model, *batch)).fetchall()
            found.update({h: np.frombuffer(v, dtype=np.float32) for h, v in rows})
        missing = sorted({k for k in keys if k not in found})
        if missing:
            by_key = {k: t for k, t in zip(keys, texts, strict=True)}
            start = time.perf_counter()
            vectors = self.inner.embed_documents([by_key[k] for k in missing])
            self.stats["seconds"] += time.perf_counter() - start
            self.db.executemany("INSERT OR REPLACE INTO vectors VALUES (?, ?, ?)",
                                [(self.model, k, v.tobytes()) for k, v in zip(missing, vectors, strict=True)])
            self.db.commit()
            found.update(dict(zip(missing, vectors, strict=True)))
            log.info("embedded %d texts in %.1fs", len(missing), self.stats["seconds"])
        self.stats["cached"] += len(keys) - len(missing)
        self.stats["embedded"] += len(missing)
        return np.stack([found[k] for k in keys]) if keys else np.zeros((0, self.dim), np.float32)

    def embed_query(self, text: str) -> np.ndarray:
        return self.inner.embed_query(text)


def build(spec: EmbedderSpec) -> Embedder:
    if spec.provider == "ollama":
        return OllamaEmbedder(spec)
    if spec.provider == "fake":
        return FakeEmbedder(spec.dim)
    if spec.provider == "nomic_api":
        return NomicApiEmbedder(spec)
    return SentenceTransformerEmbedder(spec)


def get_embedder(cfg: EmbeddingsConfig, provider: str | None = None) -> Embedder:
    """Configured embedder, falling back to the small model if it cannot load."""
    spec: EmbedderSpec = cfg
    provider = provider or os.getenv("EMBEDDINGS_PROVIDER")
    if provider == "hosted" and cfg.hosted:
        spec = cfg.hosted
    elif provider == "ollama" and cfg.ollama:
        spec = cfg.ollama
    elif provider == "fallback" and cfg.fallback:
        spec = cfg.fallback
    try:
        inner = build(spec)
    except (ImportError, OSError, RuntimeError, MemoryError) as err:
        if not cfg.fallback or spec is cfg.fallback:
            raise
        log.warning("embedder %s failed (%s), using %s", spec.model, err, cfg.fallback.model)
        inner = build(cfg.fallback)
    return CachedEmbedder(inner, cfg.cache_path)
