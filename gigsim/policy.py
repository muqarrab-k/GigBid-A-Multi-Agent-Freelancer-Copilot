import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Tier(Strict):
    max_budget: float | None = None
    connects: int = Field(gt=0)


class ConnectsPolicy(Strict):
    unit_price_usd: float = Field(ge=0)
    hourly_default: int = Field(gt=0)
    unknown_default: int = Field(gt=0)
    fixed_tiers: list[Tier] = Field(min_length=1)
    weekly_refill: Literal["reset", "add"]
    refill_weekday: Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


class ProposalPolicy(Strict):
    min_words: int = Field(ge=0)
    max_words: int = Field(gt=0)
    max_submissions_per_day: int = Field(gt=0)


class BannedRule(Strict):
    id: str
    description: str
    pattern: str
    min_digits: int | None = None

    def matches(self, text: str) -> str | None:
        for match in re.finditer(self.pattern, text):
            found = match.group(0)
            if self.min_digits and sum(c.isdigit() for c in found) < self.min_digits:
                continue
            return found
        return None


class Policy(Strict):
    version: str
    effective: str
    connects: ConnectsPolicy
    proposals: ProposalPolicy
    banned_content: list[BannedRule]

    def connects_for(self, job: dict[str, Any]) -> int:
        """Connects to submit on a job."""
        rule = self.connects
        if job.get("budget_type") == "hourly":
            return rule.hourly_default
        budget = job.get("budget_max")
        if job.get("budget_type") != "fixed" or budget is None:
            return rule.unknown_default
        for tier in rule.fixed_tiers:
            if tier.max_budget is None or budget <= tier.max_budget:
                return tier.connects
        return rule.unknown_default

    def content_violation(self, texts: list[str]) -> tuple[str, str] | None:
        for rule in self.banned_content:
            for text in texts:
                if rule.matches(text):
                    return rule.id, rule.description
        return None

    def proposal_violation(self, text: str, answers: list[str], sent_today: int) -> tuple[str, str] | None:
        words = len(text.split())
        limits = self.proposals
        if words < limits.min_words:
            return "proposal_too_short", f"cover letter has {words} words, minimum {limits.min_words}"
        if words > limits.max_words:
            return "proposal_too_long", f"cover letter has {words} words, maximum {limits.max_words}"
        if sent_today >= limits.max_submissions_per_day:
            return "max_submissions_per_day", f"limit of {limits.max_submissions_per_day} submissions per day reached"
        return self.content_violation([text, *answers])


def available(policies_dir: Path) -> list[str]:
    return sorted(p.stem for p in policies_dir.glob("*.yaml"))


@lru_cache(maxsize=8)
def load_policy(policies_dir: Path, version: str) -> Policy:
    path = policies_dir / f"{version}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"policy {version} not found in {policies_dir}")
    return Policy.model_validate(yaml.safe_load(path.read_text()))
