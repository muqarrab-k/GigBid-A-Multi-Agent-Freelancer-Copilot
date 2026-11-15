"""Compliance Guard: the policy pack as rules; clean what can be cleaned, block the rest."""

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from langgraph.runtime import Runtime
from pydantic import BaseModel, Field

from agent.handoffs import ComplianceVerdict
from agent.nodes.common import BidContext, structured, tokens_used
from agent.nodes.verifier import editing
from agent.state import BidState
from rag.verify import sentences

# checked from the verifier, not by keywords
SKIP_RULES = {"no_fabrication"}


class Violation(BaseModel):
    sentence: int = Field(ge=1)
    rule: str


class ComplianceLLMOut(BaseModel):
    violations: list[Violation] = Field(default_factory=list, max_length=20)


@lru_cache(maxsize=2)
def load_rules(path: Path) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = yaml.safe_load(path.read_text())["rules"]
    return [r for r in rules if "proposal" in r.get("applies_to", []) and r["id"] not in SKIP_RULES]


def rule_hits(text: str, rule: dict[str, Any]) -> bool:
    hints = rule.get("hints", {})
    if any(re.search(p, text) for p in hints.get("patterns", [])):
        return True
    low = text.lower()
    return any(re.search(rf"(?<![a-z0-9]){re.escape(k.lower())}(?![a-z0-9])", low) for k in hints.get("keywords", []))


def scan(texts: list[str], rules: list[dict[str, Any]]) -> list[tuple[int, str]]:
    return [(i, r["id"]) for i, t in enumerate(texts) for r in rules if rule_hits(t, r)]


async def compliance(state: BidState, runtime: Runtime[BidContext]) -> dict[str, Any]:
    ctx, draft, cfg = runtime.context, state["draft"], runtime.context.settings.compliance
    rules = load_rules(cfg.policy_rules_path)
    parts = [s for p in draft.paragraphs for s in sentences(p)] + list(draft.screening_answers)
    hits = scan(parts, rules)
    events: list[dict[str, Any]] = []
    flagged = {i for i, _ in hits}
    borderline = [i for i, t in enumerate(parts) if i not in flagged
                  and any(b.lower() in t.lower() for b in cfg.borderline_terms)]
    if borderline:
        listing = "\n".join(f"{n + 1}. {parts[i]}" for n, i in enumerate(borderline))
        out, events, _ = await structured(ctx, "compliance", ComplianceLLMOut, sentences=listing)
        for v in out.violations if out else []:
            if 1 <= v.sentence <= len(borderline):
                hits.append((borderline[v.sentence - 1], v.rule))
    report = state.get("verification")
    notes = []
    if report and report.unsupported_after:
        if editing(state):
            notes.append("edited text keeps claims the evidence does not show")
        else:
            hits.append((-1, "no_fabrication"))
    violations = [f"{rule}: {parts[i][:120] if i >= 0 else 'unsupported claims remain'}" for i, rule in hits]
    blocking = [rule for _, rule in hits if rule not in cfg.clean_rules]
    drop = {i for i, rule in hits if rule in cfg.clean_rules}
    n_body = sum(len(sentences(p)) for p in draft.paragraphs)
    kept = [t for i, t in enumerate(parts[:n_body]) if i not in drop]
    answers = [t for i, t in enumerate(parts[n_body:], start=n_body) if i not in drop]
    # a safe version for the UI: every flagged sentence cut
    flagged_all = {i for i, _ in hits}
    cleaned = " ".join(t for i, t in enumerate(parts[:n_body]) if i not in flagged_all)
    verdict = ComplianceVerdict(verdict="blocked" if blocking else "allowed", violations=violations, cleaned_text=cleaned)
    update: dict[str, Any] = {"compliance": verdict, "notes": notes, "step_count": 1, "trace": events,
                              "token_count": tokens_used(events)}
    if blocking:
        return {**update, "status": "blocked", "errors": [f"compliance blocked: {sorted(set(blocking))}"]}
    if drop:
        paragraphs = [" ".join(s for s in sentences(p) if s in kept) for p in draft.paragraphs]
        paragraphs = [p for p in paragraphs if p]
        update["draft"] = draft.model_copy(update={"paragraphs": paragraphs, "cover_letter": "\n\n".join(paragraphs),
                                                   "screening_answers": answers})
    return update


def after_compliance(state: BidState) -> str:
    return "end" if state.get("status") == "blocked" else "prepare_approval"
