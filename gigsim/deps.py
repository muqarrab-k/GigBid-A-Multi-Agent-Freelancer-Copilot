import asyncio
import hashlib
import json
import threading
import time
from collections.abc import Callable
from typing import Any

from fastapi import Header, Request
from fastapi.responses import JSONResponse

from gigsim.clients import rng_for
from gigsim.settings import Settings
from gigsim.sim import Sim
from gigsim.store import Store


class ApiError(Exception):
    def __init__(self, status: int, code: str, detail: str, headers: dict[str, str] | None = None,
                 **extra: Any) -> None:
        self.status, self.code, self.detail = status, code, detail
        self.headers = headers or {}
        self.extra = extra


def error_body(code: str, detail: object, **extra: Any) -> dict[str, Any]:
    return {"error": code, "detail": detail, **extra}


class TokenBucket:
    """Per-token bucket on the real clock."""

    def __init__(self, capacity: int, refill_per_second: float) -> None:
        self.capacity, self.rate = capacity, refill_per_second
        self.buckets: dict[str, tuple[float, float]] = {}
        self.lock = threading.Lock()

    def take(self, token: str) -> float:
        """Seconds to wait, 0 if allowed."""
        with self.lock:
            now = time.monotonic()
            level, last = self.buckets.get(token, (float(self.capacity), now))
            level = min(self.capacity, level + (now - last) * self.rate)
            if level >= 1:
                self.buckets[token] = (level - 1, now)
                return 0.0
            self.buckets[token] = (level, now)
            return (1 - level) / self.rate


class Context:
    """Everything a request handler needs."""

    def __init__(self, settings: Settings, store: Store) -> None:
        self.settings = settings
        self.store = store
        self.sim = Sim(store, settings)
        self.limiter = TokenBucket(settings.rate_limit.capacity, settings.rate_limit.refill_per_second)
        self.requests = 0
        self.lock = threading.Lock()

    def chaos_roll(self) -> tuple[bool, float]:
        """Seeded: (fail?, latency seconds) for the next request."""
        with self.lock:
            self.requests += 1
            n = self.requests
        rng = rng_for(self.store.meta("seed"), "chaos", n)
        chaos = self.settings.chaos
        return rng.random() < chaos.error_rate, rng.uniform(0, chaos.latency_ms_max) / 1000


def ctx(request: Request) -> Context:
    context: Context = request.app.state.ctx
    return context


def bearer(request: Request) -> str:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise ApiError(401, "unauthorized", "missing bearer token")
    return header[7:].strip()


async def account(request: Request) -> dict[str, Any]:
    """Auth, rate limit, latency and seeded 5xx."""
    c = ctx(request)
    token = bearer(request)
    row = c.store.one("SELECT * FROM accounts WHERE token = ?", (token,))
    if row is None:
        raise ApiError(401, "unauthorized", "unknown token")
    wait = c.limiter.take(token)
    if wait:
        raise ApiError(429, "rate_limited", "too many requests", headers={"Retry-After": str(max(1, round(wait)))})
    fail, delay = c.chaos_roll()
    if delay:
        await asyncio.sleep(delay)
    if fail:
        raise ApiError(503, "service_unavailable", "temporary error, retry with backoff",
                       headers={"Retry-After": "1"})
    return row


def admin(request: Request) -> None:
    if bearer(request) != ctx(request).settings.auth.admin_token:
        raise ApiError(401, "unauthorized", "admin token required")


def idempotency_key(key: str | None = Header(default=None, alias="Idempotency-Key")) -> str:
    if not key:
        raise ApiError(400, "idempotency_key_required", "writes need an Idempotency-Key header")
    if len(key) > 200:
        raise ApiError(422, "validation_error", "Idempotency-Key longer than 200 characters")
    return key


def idempotent(c: Context, account_id: str, key: str, payload: dict[str, Any],
               handler: Callable[[], tuple[int, dict[str, Any]]]) -> JSONResponse:
    """Replay the stored response for a repeated key."""
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    with c.store.lock:
        row = c.store.one("SELECT * FROM idempotency WHERE account_id = ? AND key = ?", (account_id, key))
        if row:
            if row["request_hash"] != digest:
                raise ApiError(409, "idempotency_key_reused", "this key was used with a different request")
            return JSONResponse(json.loads(row["body"]), status_code=row["status_code"],
                                headers={"Idempotent-Replayed": "true"})
        status, body = handler()
        c.store.execute("INSERT INTO idempotency VALUES (?, ?, ?, ?, ?)",
                        (account_id, key, digest, status, json.dumps(body)))
        return JSONResponse(body, status_code=status)
