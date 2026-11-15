from rag.index.store import Filters
from rag.variants.base import EvidenceHit, Job, Variant


class TypeFilter:
    """Portfolio types only, unless the caller names types."""

    name = "filter"

    def __init__(self, inner: Variant, types: list[str]) -> None:
        self.inner, self.types = inner, types

    def retrieve(self, job: Job, persona: str, k: int, filters: Filters | None = None) -> list[EvidenceHit]:
        if filters is None:
            filters = Filters(types=self.types)
        elif not filters.types:
            filters = filters.model_copy(update={"types": self.types})
        return self.inner.retrieve(job, persona, k, filters)
