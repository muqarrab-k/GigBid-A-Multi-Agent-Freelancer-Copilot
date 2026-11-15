from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from rag.index.bm25 import tokenize
from rag.index.store import Filters
from rag.variants.base import EvidenceHit, Job, Variant
from rag.variants.v3_rerank import Reranker, V3Rerank, brief


class CragState(TypedDict, total=False):
    job: Job
    query: Job
    persona: str
    k: int
    filters: Filters | None
    hits: list[EvidenceHit]
    passing: int
    tries: int
    grades: list[float]
    status: Literal["ok", "no_evidence"]


def rewrite(job: Job) -> str:
    """Keyword query: title, skills and requirements, no boilerplate."""
    if isinstance(job, str):
        return " ".join(dict.fromkeys(t for t in tokenize(job) if len(t) > 2))
    parts = [str(job.get("title") or ""), *map(str, job.get("skills") or []), *map(str, job.get("requirements") or [])]
    return " ".join(p for p in parts if p)


class V8Corrective:
    """Grade evidence, re-query once if weak, refuse when nothing passes."""

    name = "v8"

    def __init__(self, inner: Variant, grader: Reranker, pass_score: float, min_passing: int) -> None:
        self.inner, self.grader = inner, grader
        self.pass_score, self.min_passing = pass_score, min_passing
        # inner rerank scores are already grades
        self.pre_graded = isinstance(inner, V3Rerank) and inner.reranker is grader
        self.graph = self.build()

    def build(self) -> Any:
        g = StateGraph(CragState)
        nodes = {"retrieve": self.do_retrieve, "grade": self.grade, "rewrite": self.do_rewrite, "refuse": self.refuse}
        for name, fn in nodes.items():
            g.add_node(name, fn)  # type: ignore[call-overload]
        g.add_edge(START, "retrieve")
        g.add_edge("retrieve", "grade")
        g.add_conditional_edges("grade", self.route, {"ok": END, "rewrite": "rewrite", "refuse": "refuse"})
        g.add_edge("rewrite", "retrieve")
        g.add_edge("refuse", END)
        return g.compile()

    def do_retrieve(self, s: CragState) -> dict[str, Any]:
        return {"hits": self.inner.retrieve(s["query"], s["persona"], s["k"], s.get("filters"))}

    def do_rewrite(self, s: CragState) -> dict[str, Any]:
        return {"query": rewrite(s["job"]), "tries": s.get("tries", 0) + 1}

    def refuse(self, s: CragState) -> dict[str, Any]:
        return {"hits": [], "status": "no_evidence"}

    def grade(self, s: CragState) -> dict[str, Any]:
        hits = s["hits"]
        scores = [h.score for h in hits] if self.pre_graded else self.grader.score(brief(s["job"]), [h.text for h in hits])
        passing = sum(score >= self.pass_score for score in scores)
        return {"passing": passing, "status": "ok", "grades": [*s.get("grades", []), max(scores, default=0.0)]}

    def route(self, s: CragState) -> str:
        if s["passing"] >= self.min_passing:
            return "ok"
        return "rewrite" if s.get("tries", 0) == 0 else "refuse"

    def run(self, job: Job, persona: str, k: int, filters: Filters | None = None) -> CragState:
        return self.graph.invoke({"job": job, "query": job, "persona": persona, "k": k, "filters": filters, "tries": 0})

    def retrieve(self, job: Job, persona: str, k: int, filters: Filters | None = None) -> list[EvidenceHit]:
        return self.run(job, persona, k, filters)["hits"]
