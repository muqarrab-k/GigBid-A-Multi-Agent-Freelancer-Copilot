"""Risk Assessor: client quality plus scam, free-work, off-platform and injection flags."""

import json
import re
from datetime import date
from functools import lru_cache
from typing import Any, get_args

from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from agent.config import RiskConfig
from agent.handoffs import RiskFlag, RiskReport
from agent.nodes.common import BidContext, ToolBox, job_text, structured, tokens_used, untrusted
from agent.state import BidState

ALLOWED_FLAGS = set(get_args(RiskFlag))


class RiskLLMOut(BaseModel):
    scam_likelihood: float = Field(ge=0, le=1)
    flags: list[str] = Field(default_factory=list, max_length=8)
    injection_seen: bool = False
    red_flags: list[str] = Field(default_factory=list, max_length=5)
    explanation: str = ""


@lru_cache(maxsize=4)
def scam_terms(path: str) -> list[str]:
    try:
        return [s["term"] for s in json.loads(open(path).read())["signals"]]
    except (OSError, ValueError, KeyError):
        return []


def client_rules(client: dict[str, Any] | None, cfg: RiskConfig, today: date) -> tuple[float, list[str], list[str]]:
    """Client quality 0..1, flags and signals from public history."""
    if not client:
        return 0.5, [], ["client_history_unavailable"]
    flags, signals = [], []
    hires, posted = client.get("hires", 0), client.get("jobs_posted", 0)
    spent, rating = client.get("total_spent_usd", 0) or 0, client.get("rating")
    if not client.get("payment_verified"):
        flags.append("payment_unverified")
        signals.append("client:payment_unverified")
    since = client.get("member_since")
    if since and (today - date.fromisoformat(since)).days < cfg.client.new_account_days and hires == 0:
        signals.append("client:new_account_no_hires")
    if posted >= cfg.client.poor_history_min_posted and hires == 0:
        flags.append("poor_client_history")
        signals.append("client:many_posts_no_hires")
    if spent >= cfg.client.odd_spend_usd and hires <= 1:
        signals.append("client:odd_spend")
    quality = (0.25 * bool(client.get("payment_verified")) + 0.3 * min(hires / 10, 1)
               + 0.2 * min(spent / 10_000, 1) + 0.25 * (max(0.0, (rating - 4) / 1) if rating else 0))
    quality -= 0.2 * ("client:new_account_no_hires" in signals) + 0.2 * ("client:odd_spend" in signals)
    return round(min(1.0, max(0.0, quality)), 3), flags, signals


def text_rules(text: str, cfg: RiskConfig) -> tuple[float, list[str], list[str], bool]:
    """Pattern score, flags, signals and injection from the job text."""
    score, flags, signals = 0.0, [], []
    for rule in cfg.patterns:
        if re.search(rule.regex, text):
            score += rule.weight
            flags.append(rule.flag)
            signals.append(f"pattern:{rule.flag}")
    hits = [t for t in scam_terms(str(cfg.scam_signals_path)) if re.search(rf"\b{re.escape(t)}\b", text.lower())]
    if hits:
        score += min(cfg.scam_signal_cap, cfg.scam_signal_weight * len(hits))
        signals.append(f"scam_terms:{len(hits)}")
    injection = any(re.search(p, text) for p in cfg.injection_patterns)
    if injection:
        flags.append("injection")
        signals.append("pattern:injection")
    return min(score, 1.0), flags, signals, injection


async def risk_assessor(state: BidState, runtime: Runtime[BidContext]) -> dict[str, Any]:
    ctx, job = runtime.context, state["job"]
    cfg = ctx.settings.risk
    tools = ToolBox(ctx, "risk_assessor")
    client = None
    if job.get("client_id"):
        found = await tools.call("get_client_history", {"client_id": job["client_id"]})
        client = found.get("client") if found.get("ok") else None
    today = date.fromisoformat(state.get("today") or date.today().isoformat())
    quality, c_flags, c_signals = client_rules(client, cfg, today)
    text = job_text(job)
    t_score, t_flags, t_signals, injection = text_rules(text, cfg)

    out, events, error = await structured(ctx, "risk_assessor", RiskLLMOut,
                                          client=json.dumps(client or {}), job=untrusted(text))
    llm_score, llm_flags, signals = 0.0, [], [*c_signals, *t_signals]
    if out is not None:
        llm_score = out.scam_likelihood
        llm_flags = [f for f in out.flags if f in ALLOWED_FLAGS]
        injection = injection or out.injection_seen
        signals += [f"llm:{f}" for f in llm_flags] + (["llm:injection_seen"] if out.injection_seen else [])
    score = min(1.0, t_score + cfg.llm_weight * llm_score + 0.2 * (1 - quality) * bool(client))
    explanation = (out.explanation if out and out.explanation else "") or "rules only"
    report = RiskReport(score=round(score, 3), client_quality=quality,
                        flags=[f for f in [*c_flags, *t_flags, *llm_flags] if f in ALLOWED_FLAGS],  # type: ignore[misc]
                        injection_detected=injection, explanation=explanation[:500], signals=signals)
    update: dict[str, Any] = {"risk_report": report, "trace": [*tools.events, *events],
                              "token_count": tokens_used(events), "step_count": 1}
    if out is None:
        update["errors"] = [f"risk_assessor llm failed, rules only: {error}"]
    return update
