import json
from collections import defaultdict

from fastapi import APIRouter, Depends

from gigsim.deps import ApiError, Context, admin, ctx
from gigsim.policy import available
from gigsim.schemas import AccountStats, PolicyIn, ResetIn, StatsOut, TickIn
from gigsim.seeding import reset

router = APIRouter(prefix="/admin", dependencies=[Depends(admin)])


@router.post("/reset")
def admin_reset(body: ResetIn, c: Context = Depends(ctx)) -> dict[str, object]:
    result = reset(c.store, c.settings, body.scenario, body.seed)
    c.requests = 0
    c.limiter.buckets.clear()
    return result


@router.post("/tick")
def admin_tick(body: TickIn, c: Context = Depends(ctx)) -> dict[str, object]:
    return c.sim.tick(body.hours)


@router.post("/policy")
def admin_policy(body: PolicyIn, c: Context = Depends(ctx)) -> dict[str, object]:
    versions = available(c.settings.path(c.settings.policies_dir))
    if body.version not in versions:
        raise ApiError(422, "unknown_policy", f"policy {body.version} not found", available=versions)
    c.store.set_meta("policy", body.version)
    return {"policy": body.version}


@router.get("/stats", response_model=StatsOut)
def admin_stats(c: Context = Depends(ctx)) -> StatsOut:
    reached: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for row in c.store.query("SELECT account_id, payload FROM events WHERE type = 'proposal.status_changed'"):
        payload = json.loads(row["payload"])
        reached[row["account_id"]][payload["status"]].add(payload["proposal_id"])
    accounts = []
    for acct in c.store.query("SELECT account_id FROM accounts ORDER BY account_id"):
        aid = acct["account_id"]
        seen = reached[aid]
        spent = c.store.one("SELECT COALESCE(SUM(connects_spent), 0) AS s FROM proposals WHERE account_id = ?", (aid,))
        submitted = len(seen["submitted"])
        replied = len(seen["replied"] | seen["interview"])

        def rate(n: int, total: int = submitted) -> float:
            return round(n / total, 4) if total else 0.0

        accounts.append(AccountStats(
            account_id=aid, submitted=submitted, viewed=len(seen["viewed"]), replied=replied,
            interviews=len(seen["interview"]), hired=len(seen["hired"]), reply_rate=rate(replied),
            interview_rate=rate(len(seen["interview"])), hire_rate=rate(len(seen["hired"])),
            connects_spent=int(spent["s"]) if spent else 0,
        ))
    return StatsOut(scenario=c.store.meta("scenario"), sim_time=c.store.meta("now"),
                    policy=c.store.meta("policy"), accounts=accounts)
