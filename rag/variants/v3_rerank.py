import logging
from typing import Any, Protocol

from rag.index.store import Filters
from rag.variants.base import EvidenceHit, Job, Variant

log = logging.getLogger(__name__)


class Reranker(Protocol):
    model: str

    def score(self, query: str, texts: list[str]) -> list[float]: ...


def brief(job: Job) -> str:
    """Short query that fits the cross-encoder window."""
    if isinstance(job, str):
        return job
    skills = ", ".join(str(s) for s in job.get("skills") or [])
    reqs = "; ".join(str(r) for r in job.get("requirements") or [])
    desc = str(job.get("description") or "")[:600]
    return "\n".join(p for p in [str(job.get("title") or ""), f"Skills: {skills}" if skills else "",
                                 f"Needs: {reqs}" if reqs else "", desc] if p)


class CrossEncoderReranker:
    """Sentence-transformers cross-encoder, loaded on first use."""

    def __init__(self, names: list[str], max_length: int) -> None:
        self.names, self.max_length = [n for n in names if n], max_length
        self.encoder: Any = None
        self.model = self.names[0]
        self.seen: dict[tuple[str, str], float] = {}

    def load(self) -> Any:
        if self.encoder is None:
            from sentence_transformers import CrossEncoder
            for name in self.names:
                try:
                    self.encoder, self.model = CrossEncoder(name, max_length=self.max_length), name
                    break
                except (OSError, ValueError) as err:
                    log.warning("reranker %s failed to load: %s", name, err)
            if self.encoder is None:
                raise RuntimeError(f"no reranker could load from {self.names}")
        return self.encoder

    def score(self, query: str, texts: list[str]) -> list[float]:
        import torch
        todo = list(dict.fromkeys((query, t) for t in texts if (query, t) not in self.seen))
        if todo:
            # scores in 0..1
            scores = self.load().predict(todo, batch_size=16, activation_fn=torch.nn.Sigmoid())
            self.seen.update({pair: float(s) for pair, s in zip(todo, scores, strict=True)})
        return [self.seen[(query, t)] for t in texts]


class V3Rerank:
    """Cross-encoder rerank of the inner variant's top candidates."""

    name = "v3"

    def __init__(self, inner: Variant, reranker: Reranker, candidates: int) -> None:
        self.inner, self.reranker, self.candidates = inner, reranker, candidates

    def retrieve(self, job: Job, persona: str, k: int, filters: Filters | None = None) -> list[EvidenceHit]:
        hits = self.inner.retrieve(job, persona, max(k, self.candidates), filters)
        scores = self.reranker.score(brief(job), [h.text for h in hits])
        ranked = sorted(zip(hits, scores, strict=True), key=lambda x: (-x[1], x[0].evidence_id))[:k]
        return [h.model_copy(update={"score": round(s, 4)}) for h, s in ranked]
