import re
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from agent.config import get_config

ProposalStatus = Literal["draft", "submitted", "viewed", "replied", "interview", "hired", "lost", "ignored"]


class PortModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Job(PortModel):
    job_id: str
    title: str
    description: str | None = None
    skills: list[str] = Field(default_factory=list)
    category: str | None = None
    budget_type: Literal["fixed", "hourly"] | None = None
    budget_min: float | None = None
    budget_max: float | None = None
    hourly_min: float | None = None
    hourly_max: float | None = None
    currency: str = "USD"
    client_id: str | None = None
    client_country: str | None = None
    experience_level: str | None = None
    screening_questions: list[str] = Field(default_factory=list)
    posted_at: str | None = None
    status: str = "open"
    connects_cost: int = 0


class JobPage(PortModel):
    items: list[Job]
    total: int
    next_offset: int | None = None


class JobQuery(PortModel):
    q: str | None = None
    skills: list[str] = Field(default_factory=list)
    budget_type: Literal["fixed", "hourly"] | None = None
    min_budget: float | None = None
    max_budget: float | None = None
    min_hourly: float | None = None
    max_hourly: float | None = None
    posted_after: str | None = None
    limit: int = 20
    offset: int = 0


class ClientHistory(PortModel):
    client_id: str
    country: str | None = None
    member_since: str | None = None
    payment_verified: bool = False
    total_spent_usd: float = 0
    jobs_posted: int = 0
    hires: int = 0
    hire_rate: float = 0
    rating: float | None = None
    reviews_count: int = 0


class ConnectsBalance(PortModel):
    balance: int
    weekly_amount: int
    next_refill: str | None = None
    unit_price_usd: float = 0


class ProposalDraftIn(PortModel):
    job_id: str
    cover_letter: str
    bid_amount: float
    screening_answers: list[str] = Field(default_factory=list)


class Proposal(PortModel):
    proposal_id: str
    job_id: str
    status: ProposalStatus
    cover_letter: str
    bid_amount: float
    screening_answers: list[str] = Field(default_factory=list)
    connects_cost: int = 0
    connects_spent: int = 0
    created_at: str | None = None
    submitted_at: str | None = None
    thread_id: str | None = None


class Thread(PortModel):
    thread_id: str
    job_id: str
    client_id: str
    proposal_id: str | None = None
    created_at: str | None = None


class Message(PortModel):
    message_id: str
    thread_id: str
    sender: Literal["client", "freelancer"]
    text: str
    created_at: str | None = None


class Event(PortModel):
    event_id: int
    type: str
    data: dict[str, Any] = Field(default_factory=dict)
    sim_time: str | None = None


class EventPage(PortModel):
    events: list[Event]
    next_cursor: int


class BannedRule(PortModel):
    id: str
    description: str
    pattern: str
    min_digits: int | None = None


class Policy(PortModel):
    version: str
    connects: dict[str, Any] = Field(default_factory=dict)
    proposals: dict[str, Any] = Field(default_factory=dict)
    banned_content: list[BannedRule] = Field(default_factory=list)


class MarketStats(PortModel):
    source: str
    category: str
    budget_type: Literal["fixed", "hourly"]
    experience_level: str = "any"
    count: int
    p10: float
    p25: float
    p50: float
    p75: float
    p90: float


class Capabilities(PortModel):
    marketplace: str
    can_submit: bool
    drafts_only: bool
    requires_platform_confirmation: bool


# errors


class MarketplaceError(Exception):
    code = "marketplace_error"

    def __init__(self, detail: str = "", **extra: Any) -> None:
        super().__init__(detail or self.code)
        self.detail = detail or self.code
        self.extra = extra


class MarketplaceUnavailable(MarketplaceError):
    code = "marketplace_unavailable"

    def __init__(self, detail: str = "", retry_after: float = 30) -> None:
        super().__init__(detail, retry_after=retry_after)
        self.retry_after = retry_after


class RateLimited(MarketplaceError):
    code = "rate_limited"

    def __init__(self, detail: str = "", retry_after: float = 1) -> None:
        super().__init__(detail, retry_after=retry_after)
        self.retry_after = retry_after


class PolicyViolation(MarketplaceError):
    code = "policy_violation"

    def __init__(self, detail: str, rule_id: str) -> None:
        super().__init__(detail, rule_id=rule_id)
        self.rule_id = rule_id


class InsufficientConnects(MarketplaceError):
    code = "insufficient_connects"


class NotFound(MarketplaceError):
    code = "not_found"


class Conflict(MarketplaceError):
    code = "conflict"


class InvalidRequest(MarketplaceError):
    code = "invalid_request"


class NotConfigured(MarketplaceError):
    code = "not_configured"


@runtime_checkable
class MarketplacePort(Protocol):
    """The one interface every marketplace adapter implements."""

    capabilities: Capabilities

    async def search_jobs(self, query: JobQuery) -> JobPage: ...
    async def get_job(self, job_id: str) -> Job: ...
    async def get_client_history(self, client_id: str) -> ClientHistory: ...
    async def get_connects_balance(self) -> ConnectsBalance: ...
    async def list_proposals(self, status: str | None = None) -> list[Proposal]: ...
    async def get_proposal(self, proposal_id: str) -> Proposal: ...
    async def list_threads(self) -> list[Thread]: ...
    async def list_messages(self, thread_id: str) -> list[Message]: ...
    async def get_events(self, since: int = 0, limit: int = 50) -> EventPage: ...
    async def get_policy(self) -> Policy: ...
    async def get_market_stats(self, category: str, budget_type: str,
                               experience_level: str | None = None) -> MarketStats: ...
    async def create_proposal_draft(self, draft: ProposalDraftIn, idempotency_key: str) -> Proposal: ...
    async def submit_proposal(self, proposal_id: str, idempotency_key: str) -> Proposal: ...
    async def send_message(self, thread_id: str, text: str, idempotency_key: str) -> Message: ...
    async def aclose(self) -> None: ...


def precheck(policy: Policy, text: str, answers: list[str] | None = None,
             check_length: bool = True) -> tuple[str, str] | None:
    """Local policy check before anything is sent."""
    if check_length:
        words = len(text.split())
        low, high = policy.proposals.get("min_words"), policy.proposals.get("max_words")
        if low is not None and words < low:
            return "proposal_too_short", f"{words} words, minimum {low}"
        if high is not None and words > high:
            return "proposal_too_long", f"{words} words, maximum {high}"
    for rule in policy.banned_content:
        for chunk in [text, *(answers or [])]:
            for match in re.finditer(rule.pattern, chunk):
                if rule.min_digits and sum(c.isdigit() for c in match.group(0)) < rule.min_digits:
                    continue
                return rule.id, rule.description
    return None


def get_marketplace(token: str | None = None, **kwargs: Any) -> MarketplacePort:
    """Adapter for the configured marketplace mode."""
    mode = get_config().marketplace.mode
    if mode == "gigsim":
        from mcp_servers.marketplace.adapters.gigsim import GigSimAdapter

        return GigSimAdapter(token=token, **kwargs)
    from mcp_servers.marketplace.adapters.upwork_live import UpworkLiveAdapter

    # raises until configured
    return UpworkLiveAdapter()  # type: ignore[return-value]
