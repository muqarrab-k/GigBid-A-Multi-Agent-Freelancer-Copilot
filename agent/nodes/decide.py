"""skip / watch / bid from the transparent rules in agent/config.yaml."""

from typing import Any

from agent.config import DecisionConfig, Settings
from agent.handoffs import BidDecision, RiskReport
from agent.profile import Profile
from agent.state import BidState


def over_budget(state: BidState, settings: Settings) -> str | None:
    steps, tokens = state.get("step_count", 0), state.get("token_count", 0)
    if steps > settings.budgets.max_graph_steps:
        return f"step budget exceeded ({steps} > {settings.budgets.max_graph_steps})"
    if tokens > settings.budgets.max_tokens_per_job:
        return f"token budget exceeded ({tokens} > {settings.budgets.max_tokens_per_job})"
    return None


def budget_problem(job: dict[str, Any], profile: Profile) -> str | None:
    if job.get("budget_type") == "fixed" and job.get("budget_max") is not None and job["budget_max"] < profile.fixed_min:
        return f"fixed budget ${job['budget_max']:.0f} below floor ${profile.fixed_min:.0f}"
    if job.get("budget_type") == "hourly" and job.get("hourly_max") is not None and job["hourly_max"] < profile.hourly_floor:
        return f"hourly max ${job['hourly_max']:.0f} below floor ${profile.hourly_floor:.0f}"
    return None


def skip_flags_fired(risk: RiskReport, rules: DecisionConfig) -> list[str]:
    """Skip flags that count: rule flags always, model flags only with a rule signal beside them."""
    corroborated = bool(set(risk.signals) & set(rules.corroborating_signals))
    fired: list[str] = []
    for flag in sorted(set(risk.flags) & set(rules.skip_flags)):
        from_rule = f"pattern:{flag}" in risk.signals or f"llm:{flag}" not in risk.signals
        if from_rule or not rules.model_flags_need_rule or corroborated:
            fired.append(flag)
    return fired


def decide(state: BidState, settings: Settings, profile: Profile) -> BidDecision:
    """First matching rule wins; every rule that fired is a reason."""
    job, rules, limits = state["job"], settings.decision, settings.thresholds
    risk, fit = state.get("risk_report"), state.get("fit_report")
    reasons: list[str] = []

    def done(action: str) -> BidDecision:
        return BidDecision(job_id=job["job_id"], action=action, reasons=reasons or ["no rule fired"])  # type: ignore[arg-type]

    if risk and risk.injection_detected:
        reasons.append("job text contains instructions aimed at an AI (flagged, not followed)")
        if rules.injection_action != "flag":
            return done(rules.injection_action)
    if risk:
        bad = skip_flags_fired(risk, rules)
        if bad:
            reasons.append(f"risk flags {bad}")
            return done("skip")
        if risk.score >= limits.maximum_risk_score:
            reasons.append(f"risk {risk.score:.2f} >= {limits.maximum_risk_score}")
            return done("skip")
    if "fit_report" in state.get("failed", []) or fit is None:
        reasons.append("fit analysis failed; a human should look")
        return done("watch")
    gaps = [r.removeprefix("persona gap: ") for r in fit.reasons if r.startswith("persona gap: ")]
    if gaps and rules.skip_on_gap:
        reasons.append(f"needs {', '.join(gaps)}, a listed gap")
        return done("skip")
    problem = budget_problem(job, profile) if rules.require_budget_over_floor else None
    if problem:
        reasons.append(problem)
        return done("skip")
    if int(job.get("connects_cost") or 0) > settings.bidding_rules.max_connects_per_job:
        reasons.append(f"{job['connects_cost']} Connects is above the per-job limit {settings.bidding_rules.max_connects_per_job}")
        return done("watch")
    if fit.score >= limits.minimum_fit_score:
        reasons.append(f"fit {fit.score:.2f} >= {limits.minimum_fit_score}")
        return done("bid")
    if fit.score >= limits.watch_fit_score:
        reasons.append(f"fit {fit.score:.2f} in the watch band [{limits.watch_fit_score}, {limits.minimum_fit_score})")
        return done("watch")
    reasons.append(f"fit {fit.score:.2f} < {limits.watch_fit_score}")
    if not settings.autonomy.auto_skip_low_fit:
        reasons.append("auto-skip is off for this user; a human decides")
        return done("watch")
    return done("skip")
