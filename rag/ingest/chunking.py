import re
from typing import Protocol

from agent.config import ChunkingConfig
from rag.ingest.documents import Chunk, Document

WORD_RE = re.compile(r"\S+")


class Chunker(Protocol):
    def split(self, doc: Document) -> list[Chunk]: ...


def make_chunk(doc: Document, index: int, text: str) -> Chunk:
    meta = doc.model_dump(exclude={"text", "extra"})
    return Chunk(**meta, chunk_id=f"{doc.evidence_id}::{index}", chunk_index=index, text=text,
                 content_hash=doc.content_hash)


class FixedChunker:
    """Fixed word windows with overlap; keeps the original spacing."""

    def __init__(self, size_words: int, overlap_words: int) -> None:
        self.size, self.step = size_words, size_words - overlap_words

    def split(self, doc: Document) -> list[Chunk]:
        spans = [m.span() for m in WORD_RE.finditer(doc.text)]
        if not spans:
            return []
        chunks = []
        for i, start in enumerate(range(0, len(spans), self.step)):
            window = spans[start : start + self.size]
            chunks.append(make_chunk(doc, i, doc.text[window[0][0] : window[-1][1]]))
            if start + self.size >= len(spans):
                break
        return chunks


# code-aware and multi-vector chunkers plug in here later
CHUNKERS = {"fixed": FixedChunker}


def get_chunker(cfg: ChunkingConfig) -> Chunker:
    return CHUNKERS[cfg.strategy](cfg.size_words, cfg.overlap_words)
