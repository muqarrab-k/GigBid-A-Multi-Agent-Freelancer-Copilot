from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from agent.config import ROOT

PERSONAS = ("ai_ml", "fullstack", "data_analyst")
PERSONAS_DIR = ROOT / "data" / "personas"


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Skill(Strict):
    name: str
    level: Literal["expert", "proficient", "familiar"]
    aliases: list[str] = Field(default_factory=list)

    @property
    def terms(self) -> list[str]:
        return [self.name.lower(), *(a.lower() for a in self.aliases)]


class Rate(Strict):
    hourly_floor: float = Field(gt=0)
    hourly_target: float = Field(gt=0)
    fixed_min: float = Field(gt=0)


class Project(Strict):
    id: str
    title: str
    client: str
    client_industry: str
    start: str = Field(pattern=r"^\d{4}-\d{2}$")
    end: str = Field(pattern=r"^\d{4}-\d{2}$")
    engagement: Literal["fixed", "hourly"]
    stack: list[str] = Field(min_length=1)
    implied_skills: list[str] = Field(default_factory=list)
    built: str
    metrics: list[str] = Field(min_length=1)
    repo: str | None = None

    @property
    def skills(self) -> list[str]:
        return [*self.stack, *self.implied_skills]

    @property
    def named_client(self) -> bool:
        return self.client != "confidential"


class RepoFile(Strict):
    path: str
    purpose: str


class Repo(Strict):
    name: str
    project: str
    files: list[RepoFile] = Field(min_length=2, max_length=3)


class Facts(Strict):
    synthetic: Literal[True]
    persona: str
    name: str
    fictional: Literal[True]
    headline: str
    location: str
    timezone: str
    years_experience: int = Field(gt=0)
    languages: list[str]
    rate: Rate
    weekly_connects_budget: int = Field(gt=0)
    education: str
    skills: list[Skill] = Field(min_length=5)
    gaps: list[str] = Field(min_length=3)
    projects: list[Project] = Field(min_length=15, max_length=25)
    repos: list[Repo] = Field(min_length=6, max_length=10)

    @model_validator(mode="after")
    def check_links(self) -> "Facts":
        ids = [p.id for p in self.projects]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate project ids")
        for project in self.projects:
            if project.end < project.start:
                raise ValueError(f"{project.id} ends before it starts")
        for repo in self.repos:
            if repo.project not in ids:
                raise ValueError(f"repo {repo.name} points to unknown project {repo.project}")
        names = {s.name.lower() for s in self.skills}
        clash = names & {g.lower() for g in self.gaps}
        if clash:
            raise ValueError(f"skills listed as gaps too: {sorted(clash)}")
        return self

    def project(self, project_id: str) -> Project:
        return next(p for p in self.projects if p.id == project_id)


def facts_path(persona: str, root: Path = PERSONAS_DIR) -> Path:
    return root / persona / "facts.yaml"


def load_facts(persona: str, root: Path = PERSONAS_DIR) -> Facts:
    return Facts.model_validate(yaml.safe_load(facts_path(persona, root).read_text()))
