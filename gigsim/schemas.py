from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")
ProposalStatus = Literal["draft", "submitted", "viewed", "replied", "interview", "hired", "lost", "ignored"]


class Out(BaseModel):
    # response models drop unknown fields
    model_config = ConfigDict(extra="ignore")


class In(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Page(Out, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
    next_offset: int | None


class JobOut(Out):
    job_id: str
    title: str
    description: str | None
    skills: list[str]
    category: str | None
    budget_type: Literal["fixed", "hourly"] | None
    budget_min: float | None
    budget_max: float | None
    hourly_min: float | None
    hourly_max: float | None
    currency: str
    client_id: str | None
    client_country: str | None
    experience_level: str | None
    screening_questions: list[str]
    posted_at: str | None
    status: Literal["open", "closed"]
    connects_cost: int


class ClientOut(Out):
    client_id: str
    country: str | None
    member_since: str
    payment_verified: bool
    total_spent_usd: float
    jobs_posted: int
    hires: int
    hire_rate: float
    rating: float | None
    reviews_count: int


class AccountOut(Out):
    account_id: str
    persona: str
    name: str
    connects: int


class ConnectsOut(Out):
    balance: int
    weekly_amount: int
    next_refill: str
    unit_price_usd: float


class DraftIn(In):
    job_id: str = Field(min_length=1, max_length=64)
    cover_letter: str = Field(min_length=1, max_length=20000)
    bid_amount: float = Field(gt=0, le=1_000_000)
    screening_answers: list[str] = Field(default_factory=list, max_length=10)


class PolicyCheck(Out):
    rule_id: str
    detail: str


class ProposalOut(Out):
    proposal_id: str
    job_id: str
    status: ProposalStatus
    cover_letter: str
    bid_amount: float
    screening_answers: list[str]
    connects_cost: int
    connects_spent: int
    created_at: str
    submitted_at: str | None
    updated_at: str | None
    thread_id: str | None
    policy_check: PolicyCheck | None = None


class ThreadOut(Out):
    thread_id: str
    job_id: str
    client_id: str
    proposal_id: str
    created_at: str


class MessageIn(In):
    text: str = Field(min_length=1, max_length=5000)


class MessageOut(Out):
    message_id: str
    thread_id: str
    sender: Literal["client", "freelancer"]
    text: str
    created_at: str


class EventOut(Out):
    event_id: int
    type: str
    data: dict[str, Any]
    sim_time: str


class EventsOut(Out):
    events: list[EventOut]
    next_cursor: int


class HealthOut(Out):
    status: str
    sim_time: str
    scenario: str
    policy: str
    client_mode: str


class ResetIn(In):
    scenario: Literal["live", "dev"] = "live"
    seed: int | None = None


class TickIn(In):
    hours: int = Field(ge=1, le=2000)


class PolicyIn(In):
    version: str = Field(pattern=r"^v\d+$")


class AccountStats(Out):
    account_id: str
    submitted: int
    viewed: int
    replied: int
    interviews: int
    hired: int
    reply_rate: float
    interview_rate: float
    hire_rate: float
    connects_spent: int


class StatsOut(Out):
    scenario: str
    sim_time: str
    policy: str
    accounts: list[AccountStats]
