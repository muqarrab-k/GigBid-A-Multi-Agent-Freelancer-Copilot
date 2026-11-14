"""The freelancer profile a graph run works for (from data/personas/<persona>/facts.yaml)."""

from functools import lru_cache

import yaml
from pydantic import BaseModel, Field

from agent.config import ROOT

PERSONAS_DIR = ROOT / "data" / "personas"


class Profile(BaseModel):
    persona: str
    name: str
    hourly_floor: float
    hourly_target: float
    fixed_min: float
    weekly_connects_budget: int
    gaps: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)


@lru_cache(maxsize=16)
def load_profile(persona: str) -> Profile:
    facts = yaml.safe_load((PERSONAS_DIR / persona / "facts.yaml").read_text())
    rate = facts["rate"]
    return Profile(persona=persona, name=facts["name"], hourly_floor=rate["hourly_floor"],
                   hourly_target=rate["hourly_target"], fixed_min=rate["fixed_min"],
                   weekly_connects_budget=facts["weekly_connects_budget"], gaps=facts.get("gaps", []),
                   skills=[s["name"] for s in facts.get("skills", [])])
