import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field


class Document(BaseModel):
    """One evidence item, ready to chunk."""

    evidence_id: str
    persona: str
    type: str
    text: str
    project: str | None = None
    skills: list[str] = Field(default_factory=list)
    date: str | None = None
    client_industry: str | None = None
    outcome: str | None = None
    source_path: str
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        """Changes when text or metadata changes."""
        meta = self.model_dump(exclude={"text"})
        raw = self.text + json.dumps(meta, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()


class Chunk(BaseModel):
    chunk_id: str
    evidence_id: str
    chunk_index: int
    text: str
    persona: str
    type: str
    project: str | None = None
    skills: list[str] = Field(default_factory=list)
    date: str | None = None
    client_industry: str | None = None
    outcome: str | None = None
    source_path: str
    content_hash: str

    @property
    def text_hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()
