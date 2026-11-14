"""Pricing Strategist: bid from market stats, client spend and the floor; is the Connects cost worth it."""

from typing import Any

from langgraph.runtime import Runtime

from agent.handoffs import PriceQuote
from agent.nodes.common import BidContext, ToolBox
from agent.profile import Profile, load_profile
from agent.state import BidState


def rounded(value: float, step: int) -> float:
    return float(max(step, round(value / step) * step)) if value >= step else round(value, 2)


def suggest(job: dict[str, Any], profile: Profile, stats: dict[str, Any] | None, client_spend: float,
            step: int) -> tuple[float, str, list[str]]:
    """Amount, billing and the reasons behind it."""
    hourly = job.get("budget_type") == "hourly"
    floor = profile.hourly_floor if hourly else profile.fixed_min
    posted = job.get("hourly_max") if hourly else job.get("budget_max")
    notes = []
    if stats:
        notes.append(f"market {stats['category']} {stats['budget_type']} p25-p75 ${stats['p25']:.0f}-${stats['p75']:.0f} "
                     f"({stats['source']}, n={stats['count']})")
    if posted:
        anchor, why = float(posted), f"client posted up to ${posted:.0f}"
    elif stats:
        # richer clients get the upper quartile
        anchor = stats["p75"] if client_spend >= 10_000 else stats["p50"]
        why = f"no posted budget; market {'p75 (client spent $10k+)' if client_spend >= 10_000 else 'p50'}"
    else:
        anchor, why = profile.hourly_target if hourly else profile.fixed_min * 2, "no budget or market data; persona target"
    amount = min(anchor, profile.hourly_target) if hourly and posted else anchor
    notes.append(why)
    if amount < floor:
        notes.append(f"raised to the persona floor ${floor:.0f}")
        amount = floor
    return rounded(amount, step), "hourly" if hourly else "fixed", notes


async def pricing(state: BidState, runtime: Runtime[BidContext]) -> dict[str, Any]:
    ctx, job = runtime.context, state["job"]
    cfg = ctx.settings
    profile = load_profile(ctx.persona)
    tools = ToolBox(ctx, "pricing")
    kind = job.get("budget_type") or "hourly"
    stats_out = await tools.call("get_market_stats", {"category": ctx.persona, "budget_type": kind,
                                                      "experience_level": job.get("experience_level")})
    stats = stats_out.get("stats") if stats_out.get("ok") else None
    client = (await tools.call("get_client_history", {"client_id": job["client_id"]})).get("client") if job.get("client_id") else None
    balance_out = await tools.call("get_connects_balance", {})
    balance = (balance_out.get("connects") or {}).get("balance", profile.weekly_connects_budget)

    amount, billing, notes = suggest(job, profile, stats, (client or {}).get("total_spent_usd", 0), cfg.pricing.round_to)
    cost = int(job.get("connects_cost") or 0)
    reserve = cfg.pricing.connects_reserve_share * profile.weekly_connects_budget
    fit = state["fit_report"].score if state.get("fit_report") else 0.0
    worth = fit >= cfg.thresholds.minimum_fit_score and balance - cost >= reserve
    notes.append(f"{cost} Connects (${cost * cfg.bidding_rules.connects_unit_cost_usd:.2f}), balance {balance}, "
                 f"keeps reserve {reserve:.0f}: {'worth it' if worth else 'not worth it'} at fit {fit:.2f}")
    quote = PriceQuote(amount=amount, billing=billing, rationale="; ".join(notes), connects_cost=cost,  # type: ignore[arg-type]
                       connects_worth_it=worth)
    return {"price_quote": quote, "status": "ready_for_writer", "trace": tools.events, "step_count": 1}
