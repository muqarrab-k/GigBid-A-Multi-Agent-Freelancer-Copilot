"""Job Analyst: structured JobSpec from the job post. No tools."""

from typing import Any

from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from agent.handoffs import JobSpec
from agent.nodes.common import BidContext, job_text, structured, tokens_used, untrusted
from agent.state import BidState


class AnalystOut(BaseModel):
    deliverables: list[str] = Field(default_factory=list, max_length=8)
    requirements: list[str] = Field(default_factory=list, max_length=8)
    required_skills: list[str] = Field(default_factory=list, max_length=15)
    timeline_days: int | None = Field(default=None, ge=0, le=730)
    screening_questions: list[str] = Field(default_factory=list, max_length=10)
    hidden_needs: list[str] = Field(default_factory=list, max_length=4)


def to_spec(job: dict[str, Any], out: AnalystOut) -> JobSpec:
    """Model output for the text, real job data for the numbers."""
    low = job.get("budget_min") if job.get("budget_type") == "fixed" else job.get("hourly_min")
    high = job.get("budget_max") if job.get("budget_type") == "fixed" else job.get("hourly_max")
    return JobSpec(job_id=job["job_id"], title=job["title"], client_id=job.get("client_id"),
                   deliverables=out.deliverables, required_skills=out.required_skills or job.get("skills", []),
                   requirements=out.requirements, budget_min=low, budget_max=high,
                   timeline_days=out.timeline_days,
                   screening_questions=job.get("screening_questions") or out.screening_questions,
                   hidden_needs=out.hidden_needs, connects_cost=job.get("connects_cost") or 0)


async def analyst(state: BidState, runtime: Runtime[BidContext]) -> dict[str, Any]:
    job = state["job"]
    out, events, error = await structured(runtime.context, "analyst", AnalystOut, job=untrusted(job_text(job)))
    update: dict[str, Any] = {"trace": events, "token_count": tokens_used(events), "step_count": 1}
    if out is None:
        return {**update, "failed": ["job_spec"], "errors": [f"analyst: {error}"]}
    return {**update, "job_spec": to_spec(job, out)}
