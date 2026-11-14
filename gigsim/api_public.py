import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from gigsim.deps import ApiError, Context, account, ctx, idempotency_key, idempotent
from gigsim.schemas import (
    AccountOut,
    ClientOut,
    ConnectsOut,
    DraftIn,
    EventsOut,
    HealthOut,
    JobOut,
    MessageIn,
    MessageOut,
    Page,
    PolicyCheck,
    ProposalOut,
    ThreadOut,
)
from gigsim.store import iso

router = APIRouter()
Account = dict[str, Any]


def page_params(c: Context, limit: int | None, offset: int) -> tuple[int, int]:
    p = c.settings.pagination
    limit = p.default_limit if limit is None else limit
    if not 1 <= limit <= p.max_limit:
        raise ApiError(422, "validation_error", f"limit must be between 1 and {p.max_limit}")
    if offset < 0:
        raise ApiError(422, "validation_error", "offset must be >= 0")
    return limit, offset


def job_out(c: Context, row: dict[str, Any]) -> JobOut:
    data = json.loads(row["data"])
    return JobOut(**data, status=row["status"], posted_at=row["posted_at"],
                  connects_cost=c.sim.policy().connects_for(data))


def visible_job(c: Context, job_id: str) -> dict[str, Any]:
    row = c.store.one("SELECT * FROM jobs WHERE job_id = ? AND status != 'pending'", (job_id,))
    if row is None:
        raise ApiError(404, "not_found", f"job {job_id} not found")
    return row


def proposal_out(c: Context, row: dict[str, Any]) -> ProposalOut:
    policy = c.sim.policy()
    job = c.sim.job(row["job_id"])
    answers = json.loads(row["screening_answers"])
    check = None
    if row["status"] == "draft":
        found = policy.proposal_violation(row["cover_letter"], answers, sent_today(c, row["account_id"]))
        check = PolicyCheck(rule_id=found[0], detail=found[1]) if found else None
    return ProposalOut(**{**row, "screening_answers": answers}, connects_cost=policy.connects_for(job),
                       policy_check=check)


def owned(c: Context, table: str, key: str, value: str, acct: Account) -> dict[str, Any]:
    row = c.store.one(f"SELECT * FROM {table} WHERE {key} = ? AND account_id = ?", (value, acct["account_id"]))
    if row is None:
        raise ApiError(404, "not_found", f"{key.removesuffix('_id')} {value} not found")
    return row


def sent_today(c: Context, account_id: str) -> int:
    today = c.store.meta("now")[:10]
    row = c.store.one("SELECT COUNT(*) AS n FROM proposals WHERE account_id = ? AND substr(submitted_at, 1, 10) = ?",
                      (account_id, today))
    return int(row["n"]) if row else 0


@router.get("/health", response_model=HealthOut)
def health(c: Context = Depends(ctx)) -> HealthOut:
    return HealthOut(status="ok", sim_time=c.store.meta("now"), scenario=c.store.meta("scenario"),
                     policy=c.store.meta("policy"), client_mode=c.settings.clients.mode)


@router.get("/policy")
def policy(c: Context = Depends(ctx)) -> dict[str, Any]:
    return c.sim.policy().model_dump()


@router.get("/jobs", response_model=Page[JobOut])
def list_jobs(
    q: str | None = None,
    skills: str | None = Query(default=None, description="comma separated, any match"),
    budget_type: str | None = Query(default=None, pattern="^(fixed|hourly)$"),
    min_budget: float | None = None,
    max_budget: float | None = None,
    min_hourly: float | None = None,
    max_hourly: float | None = None,
    posted_after: datetime | None = None,
    status: str = Query(default="open", pattern="^(open|closed|any)$"),
    limit: int | None = None,
    offset: int = 0,
    acct: Account = Depends(account),
    c: Context = Depends(ctx),
) -> Page[JobOut]:
    limit, offset = page_params(c, limit, offset)
    where: list[str] = ["status != 'pending'"]
    params: list[object] = []
    if status != "any":
        where.append("status = ?")
        params.append(status)
    if q:
        where.append("(LOWER(title) LIKE ? OR LOWER(description) LIKE ?)")
        params += [f"%{q.lower()}%"] * 2
    if skills:
        names = [s.strip().lower() for s in skills.split(",") if s.strip()]
        where.append("(" + " OR ".join("LOWER(skills) LIKE ?" for _ in names) + ")")
        params += [f'%"{n}"%' for n in names]
    for clause, value in (("budget_type = ?", budget_type), ("budget_max >= ?", min_budget),
                          ("budget_max <= ?", max_budget), ("hourly_max >= ?", min_hourly),
                          ("hourly_max <= ?", max_hourly)):
        if value is not None:
            where.append(clause)
            params.append(value)
    if posted_after:
        where.append("posted_at > ?")
        params.append(iso(posted_after))
    sql = " WHERE " + " AND ".join(where)
    total = c.store.one(f"SELECT COUNT(*) AS n FROM jobs{sql}", tuple(params))
    rows = c.store.query(f"SELECT * FROM jobs{sql} ORDER BY posted_at DESC, job_id LIMIT ? OFFSET ?",
                         (*params, limit, offset))
    count = int(total["n"]) if total else 0
    return Page[JobOut](items=[job_out(c, r) for r in rows], total=count, limit=limit, offset=offset,
                        next_offset=offset + limit if offset + limit < count else None)


@router.get("/jobs/{job_id}", response_model=JobOut)
def get_job(job_id: str, acct: Account = Depends(account), c: Context = Depends(ctx)) -> JobOut:
    return job_out(c, visible_job(c, job_id))


@router.get("/clients/{client_id}", response_model=ClientOut)
def get_client(client_id: str, acct: Account = Depends(account), c: Context = Depends(ctx)) -> ClientOut:
    row = c.store.one("SELECT data FROM clients WHERE client_id = ?", (client_id,))
    if row is None:
        raise ApiError(404, "not_found", f"client {client_id} not found")
    return ClientOut(**json.loads(row["data"]))


@router.get("/me", response_model=AccountOut)
def me(acct: Account = Depends(account)) -> AccountOut:
    return AccountOut(**acct)


@router.get("/me/connects", response_model=ConnectsOut)
def my_connects(acct: Account = Depends(account), c: Context = Depends(ctx)) -> ConnectsOut:
    return ConnectsOut(balance=acct["connects"], weekly_amount=acct["weekly_connects"],
                       next_refill=c.store.meta("next_refill"),
                       unit_price_usd=c.sim.policy().connects.unit_price_usd)


@router.post("/proposals/drafts", status_code=201, response_model=ProposalOut)
def create_draft(body: DraftIn, key: str = Depends(idempotency_key), acct: Account = Depends(account),
                 c: Context = Depends(ctx)) -> JSONResponse:
    def handler() -> tuple[int, dict[str, Any]]:
        job = visible_job(c, body.job_id)
        if job["status"] != "open":
            raise ApiError(409, "job_not_open", f"job {body.job_id} is not open")
        if c.store.one("SELECT 1 FROM proposals WHERE account_id = ? AND job_id = ?",
                       (acct["account_id"], body.job_id)):
            raise ApiError(409, "proposal_exists", "you already have a proposal for this job")
        pid = c.store.next_id("pr", "proposals")
        now = c.store.meta("now")
        c.store.execute(
            "INSERT INTO proposals VALUES (?, ?, ?, 'draft', ?, ?, ?, 0, ?, NULL, NULL, NULL, ?, NULL, NULL)",
            (pid, acct["account_id"], body.job_id, body.cover_letter, body.bid_amount,
             json.dumps(body.screening_answers), now, now),
        )
        row = owned(c, "proposals", "proposal_id", pid, acct)
        return 201, proposal_out(c, row).model_dump()

    return idempotent(c, acct["account_id"], key, {"path": "drafts", **body.model_dump()}, handler)


@router.post("/proposals/{proposal_id}/submit", response_model=ProposalOut)
def submit(proposal_id: str, key: str = Depends(idempotency_key), acct: Account = Depends(account),
           c: Context = Depends(ctx)) -> JSONResponse:
    def handler() -> tuple[int, dict[str, Any]]:
        row = owned(c, "proposals", "proposal_id", proposal_id, acct)
        if row["status"] != "draft":
            raise ApiError(409, "already_submitted", f"proposal is {row['status']}")
        job = visible_job(c, row["job_id"])
        if job["status"] != "open":
            raise ApiError(409, "job_not_open", "job is no longer open")
        policy = c.sim.policy()
        found = policy.proposal_violation(row["cover_letter"], json.loads(row["screening_answers"]),
                                          sent_today(c, acct["account_id"]))
        if found:
            raise ApiError(422, "policy_violation", found[1], rule_id=found[0], policy=policy.version)
        cost = policy.connects_for(json.loads(job["data"]))
        balance = c.store.one("SELECT connects FROM accounts WHERE account_id = ?", (acct["account_id"],))
        if balance is None or balance["connects"] < cost:
            raise ApiError(402, "insufficient_connects", f"submitting costs {cost} Connects",
                           required=cost, balance=balance["connects"] if balance else 0)
        decide_at = c.sim.hours_later(c.settings.clients.view_delay_hours, proposal_id, "delay")
        now = c.store.meta("now")
        with c.store.transaction() as conn:
            conn.execute("UPDATE accounts SET connects = connects - ? WHERE account_id = ?", (cost, acct["account_id"]))
            conn.execute("UPDATE proposals SET status = 'submitted', submitted_at = ?, updated_at = ?, "
                         "decide_at = ?, connects_spent = ? WHERE proposal_id = ?",
                         (now, now, decide_at, cost, proposal_id))
        c.store.add_event(acct["account_id"], "proposal.status_changed",
                          {"proposal_id": proposal_id, "job_id": row["job_id"], "status": "submitted"})
        return 200, proposal_out(c, owned(c, "proposals", "proposal_id", proposal_id, acct)).model_dump()

    return idempotent(c, acct["account_id"], key, {"path": "submit", "proposal_id": proposal_id}, handler)


@router.get("/proposals", response_model=Page[ProposalOut])
def list_proposals(status: str | None = None, limit: int | None = None, offset: int = 0,
                   acct: Account = Depends(account), c: Context = Depends(ctx)) -> Page[ProposalOut]:
    limit, offset = page_params(c, limit, offset)
    where, params = "account_id = ?", [acct["account_id"]]
    if status:
        where += " AND status = ?"
        params.append(status)
    total = c.store.one(f"SELECT COUNT(*) AS n FROM proposals WHERE {where}", tuple(params))
    rows = c.store.query(f"SELECT * FROM proposals WHERE {where} ORDER BY proposal_id LIMIT ? OFFSET ?",
                         (*params, limit, offset))
    count = int(total["n"]) if total else 0
    return Page[ProposalOut](items=[proposal_out(c, r) for r in rows], total=count, limit=limit, offset=offset,
                             next_offset=offset + limit if offset + limit < count else None)


@router.get("/proposals/{proposal_id}", response_model=ProposalOut)
def get_proposal(proposal_id: str, acct: Account = Depends(account), c: Context = Depends(ctx)) -> ProposalOut:
    return proposal_out(c, owned(c, "proposals", "proposal_id", proposal_id, acct))


@router.get("/threads", response_model=list[ThreadOut])
def list_threads(acct: Account = Depends(account), c: Context = Depends(ctx)) -> list[ThreadOut]:
    rows = c.store.query("SELECT * FROM threads WHERE account_id = ? ORDER BY thread_id", (acct["account_id"],))
    return [ThreadOut(**r) for r in rows]


@router.get("/threads/{thread_id}/messages", response_model=list[MessageOut])
def thread_messages(thread_id: str, acct: Account = Depends(account), c: Context = Depends(ctx)) -> list[MessageOut]:
    owned(c, "threads", "thread_id", thread_id, acct)
    rows = c.store.query("SELECT * FROM messages WHERE thread_id = ? ORDER BY message_id", (thread_id,))
    return [MessageOut(**r) for r in rows]


@router.post("/threads/{thread_id}/messages", status_code=201, response_model=MessageOut)
def send_message(thread_id: str, body: MessageIn, key: str = Depends(idempotency_key),
                 acct: Account = Depends(account), c: Context = Depends(ctx)) -> JSONResponse:
    def handler() -> tuple[int, dict[str, Any]]:
        owned(c, "threads", "thread_id", thread_id, acct)
        policy = c.sim.policy()
        found = policy.content_violation([body.text])
        if found:
            raise ApiError(422, "policy_violation", found[1], rule_id=found[0], policy=policy.version)
        msg_id = c.store.next_id("msg", "messages")
        now = c.store.meta("now")
        c.store.execute("INSERT INTO messages VALUES (?, ?, 'freelancer', ?, ?, NULL, 0)",
                        (msg_id, thread_id, body.text, now))
        followup = c.sim.hours_later(c.settings.clients.followup_delay_hours, msg_id, "followup")
        c.store.execute("UPDATE threads SET followup_at = ? WHERE thread_id = ?", (followup, thread_id))
        row = c.store.one("SELECT * FROM messages WHERE message_id = ?", (msg_id,))
        return 201, MessageOut(**(row or {})).model_dump()

    return idempotent(c, acct["account_id"], key, {"path": f"threads/{thread_id}", **body.model_dump()}, handler)


@router.get("/events", response_model=EventsOut)
def events(since: int = Query(default=0, ge=0), limit: int | None = None, acct: Account = Depends(account),
           c: Context = Depends(ctx)) -> EventsOut:
    limit, _ = page_params(c, limit, 0)
    rows = c.store.query("SELECT * FROM events WHERE account_id = ? AND event_id > ? ORDER BY event_id LIMIT ?",
                         (acct["account_id"], since, limit))
    items = [{**r, "data": json.loads(r["payload"])} for r in rows]
    return EventsOut(events=items, next_cursor=items[-1]["event_id"] if items else since)
