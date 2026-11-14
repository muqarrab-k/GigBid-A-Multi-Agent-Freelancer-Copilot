import asyncio
import os
import random
from typing import Any

import httpx

from agent.config import MarketplaceConfig, get_config
from agent.marketplace_port import (
    Capabilities,
    ClientHistory,
    Conflict,
    ConnectsBalance,
    EventPage,
    InsufficientConnects,
    InvalidRequest,
    Job,
    JobPage,
    JobQuery,
    MarketplaceError,
    MarketplaceUnavailable,
    Message,
    NotFound,
    Policy,
    PolicyViolation,
    Proposal,
    ProposalDraftIn,
    RateLimited,
    Thread,
)

RETRY_STATUS = {429, 500, 502, 503, 504}


def to_error(response: httpx.Response) -> MarketplaceError:
    """GigSim error body to a typed port error."""
    try:
        body = response.json()
    except ValueError:
        body = {}
    code, detail = body.get("error", ""), str(body.get("detail", response.text))
    retry_after = float(response.headers.get("Retry-After", 1))
    status = response.status_code
    if status == 429:
        return RateLimited(detail, retry_after=retry_after)
    if status >= 500:
        return MarketplaceUnavailable(detail, retry_after=retry_after)
    if code == "policy_violation":
        return PolicyViolation(detail, rule_id=body.get("rule_id", "unknown"))
    if status == 402:
        return InsufficientConnects(detail, required=body.get("required"), balance=body.get("balance"))
    if status == 404:
        return NotFound(detail)
    if status == 409:
        return Conflict(detail, reason=code)
    if status == 401:
        return MarketplaceUnavailable(f"marketplace rejected credentials: {detail}", retry_after=300)
    return InvalidRequest(detail, reason=code)


class GigSimAdapter:
    """MarketplacePort over the GigSim HTTP API."""

    capabilities = Capabilities(marketplace="gigsim", can_submit=True, drafts_only=False,
                                requires_platform_confirmation=False)

    def __init__(self, token: str | None = None, base_url: str | None = None,
                 transport: httpx.AsyncBaseTransport | None = None,
                 settings: MarketplaceConfig | None = None) -> None:
        self.cfg = settings or get_config().marketplace
        token = token or os.getenv("GIGSIM_API_TOKEN", "")
        self.client = httpx.AsyncClient(
            base_url=base_url or self.cfg.gigsim_base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=self.cfg.timeout_s,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self.client.aclose()

    def backoff(self, attempt: int, retry_after: float | None) -> float:
        # exponential with jitter
        wait = min(self.cfg.backoff_max_s, self.cfg.backoff_s * 2**attempt) * random.uniform(0.5, 1.0)
        return max(wait, retry_after or 0)

    async def request(self, method: str, path: str, *, params: dict[str, Any] | None = None,
                      json: dict[str, Any] | None = None, idempotency_key: str | None = None) -> Any:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        last: MarketplaceError = MarketplaceUnavailable("no attempt made")
        for attempt in range(self.cfg.max_retries + 1):
            try:
                response = await self.client.request(method, path, params=params, json=json, headers=headers)
            except httpx.TransportError as err:
                last = MarketplaceUnavailable(f"cannot reach marketplace: {type(err).__name__}", retry_after=30)
                retry_after = None
            else:
                if response.status_code < 400:
                    return response.json()
                last = to_error(response)
                if response.status_code not in RETRY_STATUS:
                    raise last
                retry_after = float(response.headers.get("Retry-After", 0)) or None
            if attempt < self.cfg.max_retries:
                await asyncio.sleep(self.backoff(attempt, retry_after))
        raise last

    async def search_jobs(self, query: JobQuery) -> JobPage:
        params = query.model_dump(exclude_none=True)
        skills = params.pop("skills", [])
        if skills:
            params["skills"] = ",".join(skills)
        body = await self.request("GET", "/jobs", params=params)
        return JobPage(items=[Job(**j) for j in body["items"]], total=body["total"], next_offset=body["next_offset"])

    async def get_job(self, job_id: str) -> Job:
        return Job(**await self.request("GET", f"/jobs/{job_id}"))

    async def get_client_history(self, client_id: str) -> ClientHistory:
        return ClientHistory(**await self.request("GET", f"/clients/{client_id}"))

    async def get_connects_balance(self) -> ConnectsBalance:
        return ConnectsBalance(**await self.request("GET", "/me/connects"))

    async def list_proposals(self, status: str | None = None) -> list[Proposal]:
        params: dict[str, Any] = {"limit": 100, **({"status": status} if status else {})}
        body = await self.request("GET", "/proposals", params=params)
        return [Proposal(**p) for p in body["items"]]

    async def get_proposal(self, proposal_id: str) -> Proposal:
        return Proposal(**await self.request("GET", f"/proposals/{proposal_id}"))

    async def list_threads(self) -> list[Thread]:
        return [Thread(**t) for t in await self.request("GET", "/threads")]

    async def list_messages(self, thread_id: str) -> list[Message]:
        return [Message(**m) for m in await self.request("GET", f"/threads/{thread_id}/messages")]

    async def get_events(self, since: int = 0, limit: int = 50) -> EventPage:
        return EventPage(**await self.request("GET", "/events", params={"since": since, "limit": limit}))

    async def get_policy(self) -> Policy:
        return Policy(**await self.request("GET", "/policy"))

    async def create_proposal_draft(self, draft: ProposalDraftIn, idempotency_key: str) -> Proposal:
        body = await self.request("POST", "/proposals/drafts", json=draft.model_dump(), idempotency_key=idempotency_key)
        return Proposal(**body)

    async def submit_proposal(self, proposal_id: str, idempotency_key: str) -> Proposal:
        body = await self.request("POST", f"/proposals/{proposal_id}/submit", idempotency_key=idempotency_key)
        return Proposal(**body)

    async def send_message(self, thread_id: str, text: str, idempotency_key: str) -> Message:
        body = await self.request("POST", f"/threads/{thread_id}/messages", json={"text": text},
                                  idempotency_key=idempotency_key)
        return Message(**body)
