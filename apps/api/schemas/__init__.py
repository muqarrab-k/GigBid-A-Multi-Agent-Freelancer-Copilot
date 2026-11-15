"""Typed request and response models for the API."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from agent.handoffs import IntentLabel

Persona = Literal["ai_ml", "fullstack", "data_analyst"]


class LoginIn(BaseModel):
    username: str = Field(min_length=3, max_length=40, pattern=r"^[a-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=200)


class RegisterIn(LoginIn):
    persona: Persona


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class UserOut(BaseModel):
    username: str
    persona: str
    # from the persona fact sheet
    hourly_floor: float | None = None
    fixed_min: float | None = None


class UploadIn(BaseModel):
    filename: str = Field(min_length=1, max_length=200, pattern=r"^[\w .()-]+\.(md|txt)$")
    text: str = Field(min_length=20, max_length=200_000)
    type: Literal["case_study", "readme", "review", "cv", "document"] = "case_study"


class UploadOut(BaseModel):
    evidence_id: str
    added: int
    updated: int
    chunks: int


class JobRow(BaseModel):
    job_id: str
    title: str
    category: str | None = None
    budget_type: str | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    fit_score: float | None = None
    risk_score: float | None = None
    risk_badges: list[str] = []
    recommended_action: Literal["skip", "watch", "bid"] | None = None
    price: float | None = None
    billing: str | None = None
    connects_cost: int | None = None
    status: str | None = None
    thread_id: str | None = None


class InboxOut(BaseModel):
    items: list[JobRow]


class JobDetail(BaseModel):
    job: dict[str, Any]
    thread_id: str | None = None
    status: str | None = None
    job_spec: dict[str, Any] | None = None
    risk_report: dict[str, Any] | None = None
    evidence_matrix: list[dict[str, Any]] = []
    price_rationale: str | None = None
    price: dict[str, Any] | None = None
    decision_reasons: list[str] = []
    notes: list[str] = []
    errors: list[str] = []


class ScoutOut(BaseModel):
    found: int
    new_jobs: list[str]
    runs_started: list[str]


class RunIn(BaseModel):
    job_id: str = Field(min_length=1, max_length=64)


class RunOut(BaseModel):
    thread_id: str
    trace_id: str
    status: str
    started: bool
    events_url: str


class RunState(BaseModel):
    thread_id: str
    status: str | None
    next: list[str]
    trace_id: str | None = None
    errors: list[str] = []


class ApprovalItem(BaseModel):
    thread_id: str
    kind: Literal["bid", "conversation"]
    payload: dict[str, Any]


class ApprovalsOut(BaseModel):
    items: list[ApprovalItem]


class ApprovalIn(BaseModel):
    action: Literal["approve", "edit", "reject"]
    edited_text: str | None = Field(default=None, max_length=6000)
    reason: str | None = Field(default=None, max_length=500)


class ApprovalResult(BaseModel):
    thread_id: str
    status: str | None
    submission: dict[str, Any] | None = None
    pending: dict[str, Any] | None = None
    promoted_memory: list[str] = []
    errors: list[str] = []


class ProposalRow(BaseModel):
    proposal_id: str
    job_id: str
    status: str
    bid_amount: float | None = None
    connects_cost: int | None = None
    thread_id: str | None = None
    submitted_at: str | None = None


class ProposalsOut(BaseModel):
    items: list[ProposalRow]


class PipelineOut(BaseModel):
    counts: dict[str, int]
    proposals: list[ProposalRow]
    new_events: int
    promoted_memory: list[str] = []


class ThreadRow(BaseModel):
    thread_id: str
    proposal_id: str | None = None
    job_id: str | None = None
    conversation_id: str
    draft_status: str | None = None


class ThreadsOut(BaseModel):
    items: list[ThreadRow]


class MessageRow(BaseModel):
    message_id: str
    sender: Literal["client", "freelancer"]
    text: str
    sent_at: str | None = None
    untrusted: bool


class ThreadDetail(BaseModel):
    thread_id: str
    conversation_id: str
    messages: list[MessageRow]
    intent: IntentLabel | None = None
    flags: list[str] = []
    draft_status: str | None = None
    pending: dict[str, Any] | None = None


class DraftOut(BaseModel):
    conversation_id: str
    status: str | None
    intent: IntentLabel | None = None
    flags: list[str] = []
    pending: dict[str, Any] | None = None
    errors: list[str] = []


class CategoryStats(BaseModel):
    category: str
    submitted: int
    replied: int
    hired: int
    reply_rate: float | None
    hire_rate: float | None


class AnalyticsOut(BaseModel):
    by_category: list[CategoryStats]
    connects_by_outcome: dict[str, int]
    per_proposal: dict[str, float | None]
    rejection_reasons: list[tuple[str, int]]
    eval_files: list[dict[str, Any]]


class SavedSearch(BaseModel):
    q: str | None = Field(default=None, max_length=200)
    skills: list[str] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=20, ge=1, le=50)


class SettingsIn(BaseModel):
    auto_skip_low_fit: bool | None = None
    # sending always needs a human
    auto_send: Literal[False] | None = None
    max_tokens_per_job: int | None = Field(default=None, ge=1000, le=200000)
    max_revisions: int | None = Field(default=None, ge=0, le=3)
    weekly_connects_budget: int | None = Field(default=None, ge=0, le=500)
    saved_searches: list[SavedSearch] | None = Field(default=None, max_length=10)


class SettingsOut(BaseModel):
    auto_skip_low_fit: bool
    auto_send: Literal[False] = False
    max_tokens_per_job: int
    max_revisions: int
    weekly_connects_budget: int
    saved_searches: list[SavedSearch]


class MemoryItem(BaseModel):
    kind: Literal["style", "outcome"]
    key: str
    rule: str
    why: str
    promoted_at: str
    source_edits: list[dict[str, Any]] = []
    source_events: list[Any] = []


class MemoryOut(BaseModel):
    items: list[MemoryItem]


class StatusOut(BaseModel):
    marketplace: Literal["up", "down"]
    servers: dict[str, str]
    degraded: bool
