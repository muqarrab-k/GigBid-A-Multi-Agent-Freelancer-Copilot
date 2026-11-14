import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from pydantic import BaseModel, Field

from agent.config import get_config
from data_pipeline.common import REAL_SEED_DIR
from synth.facts import PERSONAS, PERSONAS_DIR, Facts, Project, load_facts
from synth.matching import job_text, ranked_projects

EMPHASIS = ["business impact", "the technical approach", "how the client's team works now"]
OUTCOME_SHARES = {"won": 0.15, "replied": 0.25}
LAST_DATE = date(2025, 10, 31)


class Item(BaseModel):
    """One evidence item: manifest row plus render inputs."""

    evidence_id: str
    persona: str
    type: str
    project: str | None = None
    skills: list[str] = Field(default_factory=list)
    date: str | None = None
    client_industry: str | None = None
    outcome: str | None = None
    path: str
    synthetic: bool = True
    prompt: str | None = None
    tag: str = ""
    values: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)

    def manifest_row(self, rendered: bool) -> dict[str, Any]:
        row = self.model_dump(exclude={"prompt", "tag", "values", "extra"})
        return {**row, "rendered": rendered}


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def month_after(ym: str, months: int = 1) -> str:
    year, month = map(int, ym.split("-"))
    month += months
    year += (month - 1) // 12
    return f"{year}-{(month - 1) % 12 + 1:02d}"


def project_block(project: Project) -> str:
    data = project.model_dump(exclude={"id", "repo"})
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()


def client_label(project: Project) -> str:
    if project.named_client:
        return project.client
    return f"a client in {project.client_industry} (name withheld)"


def banned(project: Project) -> str:
    return ", ".join(f'"{s}"' for s in project.implied_skills) or "none"


def persona_rng(persona: str, salt: int = 0) -> np.random.Generator:
    return np.random.default_rng([get_config().data.seed, PERSONAS.index(persona), salt])


def portfolio_items(facts: Facts) -> list[Item]:
    p, rng = facts.persona, persona_rng(facts.persona, 1)
    items = []
    for project in facts.projects:
        common = {
            "persona": p,
            "project": project.id,
            "skills": project.skills,
            "date": project.end,
            "client_industry": project.client_industry,
        }
        items.append(
            Item(
                evidence_id=f"{p}:case_study:{project.id}",
                type="case_study",
                path=f"case_studies/{project.id}-{slug(project.title)}.md",
                prompt="synth_case_study",
                tag=f"{p}/case_study",
                values={
                    "name": facts.name,
                    "headline": facts.headline,
                    "project": project_block(project),
                    "emphasis": EMPHASIS[int(rng.integers(len(EMPHASIS)))],
                    "client_label": client_label(project),
                    "banned": banned(project),
                },
                **common,
            )
        )
    for repo in facts.repos:
        project = facts.project(repo.project)
        common = {
            "persona": p,
            "project": project.id,
            "skills": project.skills,
            "date": project.end,
            "client_industry": project.client_industry,
        }
        files = "\n".join(f"- {f.path}: {f.purpose}" for f in repo.files)
        items.append(
            Item(
                evidence_id=f"{p}:readme:{repo.name}",
                type="readme",
                path=f"repos/{repo.name}/README.md",
                prompt="synth_readme",
                tag=f"{p}/readme",
                values={"repo": repo.name, "project": project_block(project), "files": files,
                        "banned": banned(project)},
                **common,
            )
        )
        for file in repo.files:
            items.append(
                Item(
                    evidence_id=f"{p}:code:{repo.name}/{file.path}",
                    type="code",
                    path=f"repos/{repo.name}/{file.path}",
                    prompt="synth_code",
                    tag=f"{p}/code",
                    values={"repo": repo.name, "path": file.path, "purpose": file.purpose,
                            "stack": ", ".join(project.stack), "built": project.built},
                    **common,
                )
            )
    return items


def review_items(facts: Facts, count: int) -> list[Item]:
    p, rng = facts.persona, persona_rng(facts.persona, 2)
    order = [facts.projects[i] for i in rng.permutation(len(facts.projects))]
    named = [x for x in order if x.named_client]
    while len(order) < count:
        order.append(named[len(order) % len(named)])
    items = []
    for n, project in enumerate(order[:count], start=1):
        rating = float(rng.choice([5.0, 4.8, 4.5, 4.0, 3.5], p=[0.62, 0.16, 0.1, 0.08, 0.04]))
        items.append(
            Item(
                evidence_id=f"{p}:review:{n:02d}",
                persona=p,
                type="review",
                project=project.id,
                skills=project.skills,
                date=month_after(project.end),
                client_industry=project.client_industry,
                path="reviews.jsonl",
                prompt="synth_review",
                tag=f"{p}/review",
                values={"name": facts.name, "project": project_block(project),
                        "client_label": client_label(project), "rating": rating,
                        "banned": banned(project)},
                extra={"rating": rating, "client": project.client},
            )
        )
    return items


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def style_text(f: dict[str, Any], cited: list[Project]) -> str:
    lines = []
    if f["opens_with_problem"]:
        lines.append("- Open by restating the client's specific problem in one sentence.")
    elif f["generic"]:
        lines.append("- Open with a generic line about being passionate and hard-working.")
    else:
        lines.append("- Open by briefly introducing yourself.")
    if cited:
        names = "; ".join(f"{p.title} ({p.id})" for p in cited)
        lines.append(f"- Mention these projects by what was built and one result each: {names}.")
    else:
        lines.append("- Do not mention any specific past project or client.")
    if f["generic"]:
        lines.append("- Prefer broad claims like 'extensive experience' over specifics.")
    lines.append("- Keep it under 150 words." if f["short"] else "- Write 300 to 380 words.")
    if f["question"]:
        lines.append("- End with one specific question about the job.")
    return "\n".join(lines)


def proposal_items(facts: Facts, history: list[dict[str, Any]], count: int) -> list[Item]:
    """Past proposals on real history jobs, outcomes from a noisy rule."""
    cfg = get_config().synth
    p, rng = facts.persona, persona_rng(facts.persona, 3)
    on_topic = sorted((j for j in history if p in j["persona_tags"]), key=lambda j: j["job_id"])
    off_topic = sorted((j for j in history if not j["persona_tags"]), key=lambda j: j["job_id"])
    n_off = count // 15
    picks = [on_topic[i] for i in rng.choice(len(on_topic), count - n_off, replace=False)]
    picks += [off_topic[i] for i in rng.choice(len(off_topic), n_off, replace=False)]

    rows = []
    for job in picks:
        ranked = ranked_projects(job_text(job), facts, limit=2)
        n_cite = min(len(ranked), int(rng.choice([0, 1, 2], p=[0.3, 0.4, 0.3])))
        cited = [facts.project(pid) for pid, _ in ranked[:n_cite]]
        opens = bool(rng.random() < 0.5)
        f = {
            "opens_with_problem": opens,
            "generic": bool(not opens and rng.random() < 0.6),
            "short": bool(rng.random() < 0.5),
            "question": bool(rng.random() < 0.4),
            "cites": len(cited),
            "relevance": ranked[0][1] if ranked else 0,
            "off_topic": not job["persona_tags"],
        }
        score = (
            1.3 * f["opens_with_problem"] + 0.8 * f["cites"] + 0.7 * f["short"]
            - 1.4 * f["generic"] + 0.3 * f["question"] + 0.25 * min(f["relevance"], 4)
            - 0.8 * f["off_topic"] + rng.normal(0, 0.6)
        )
        rows.append((job, cited, f, score))

    # outcome by score rank
    order = np.argsort([-r[3] for r in rows], kind="stable")
    n_won = round(len(rows) * OUTCOME_SHARES["won"])
    n_replied = round(len(rows) * OUTCOME_SHARES["replied"])
    clean = [""] * len(rows)
    for rank, i in enumerate(order):
        clean[i] = "won" if rank < n_won else "replied" if rank < n_won + n_replied else "ignored"

    items = []
    for n, ((job, cited, f, score), outcome) in enumerate(zip(rows, clean, strict=True), start=1):
        final = outcome
        noisy = bool(rng.random() < cfg.label_noise)
        if noisy:
            final = str(rng.choice([o for o in ("won", "replied", "ignored") if o != outcome]))
        after = max([c.end for c in cited], default="2021-01")
        year, month = map(int, month_after(after).split("-"))
        start = date(year, month, 1)
        day = start.toordinal() + int(rng.integers(max(1, LAST_DATE.toordinal() - start.toordinal())))
        projects_text = "\n\n".join(project_block(c) for c in cited) or "(none)"
        profile = (
            f"{facts.years_experience} years experience; skills: "
            + ", ".join(s.name for s in facts.skills if s.level == "expert")
        )
        items.append(
            Item(
                evidence_id=f"{p}:proposal:{n:03d}",
                persona=p,
                type="proposal",
                project=cited[0].id if cited else None,
                skills=sorted({s for c in cited for s in c.skills}),
                date=date.fromordinal(day).isoformat(),
                outcome=final,
                path="proposals.jsonl",
                prompt="synth_proposal",
                tag=f"{p}/proposal",
                values={"name": facts.name, "profile": profile, "job_title": job["title"],
                        "job_text": (job.get("description") or "")[:1500],
                        "projects": projects_text, "style": style_text(f, cited)},
                extra={"job_id": job["job_id"], "job_title": job["title"],
                       "job_text": job.get("description") or "",
                       "cited_projects": [c.id for c in cited],
                       "features": f, "score": round(float(score), 3),
                       "clean_outcome": outcome, "noisy": noisy},
            )
        )
    return items


def cv_item(facts: Facts) -> Item:
    return Item(evidence_id=f"{facts.persona}:cv", persona=facts.persona, type="cv",
                skills=[s.name for s in facts.skills], path="cv.pdf")


def plan_persona(persona: str, root: Path = PERSONAS_DIR, history_path: Path | None = None) -> list[Item]:
    cfg = get_config().synth
    facts = load_facts(persona, root)
    history = load_jsonl(history_path or REAL_SEED_DIR / "jobs_history.jsonl")
    return [
        cv_item(facts),
        *portfolio_items(facts),
        *review_items(facts, cfg.reviews_per_persona),
        *proposal_items(facts, history, cfg.proposals_per_persona),
    ]
