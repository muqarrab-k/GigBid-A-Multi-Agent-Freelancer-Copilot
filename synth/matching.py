import re
from functools import lru_cache
from typing import Any

from synth.facts import Facts, Project

STOPWORDS = {"with", "from", "that", "this", "your", "need", "needed", "looking", "expert",
             "help", "project", "build", "create", "using", "based", "want", "developer"}


@lru_cache(maxsize=4096)
def term_re(term: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])")


def has_term(text: str, term: str) -> bool:
    return bool(term_re(term).search(text))


def job_text(job: dict[str, Any]) -> str:
    skills = " ".join(str(s) for s in job.get("skills") or [])
    return f"{job.get('title') or ''} {skills} {job.get('description') or ''}".lower()


def skill_hits(text: str, facts: Facts) -> list[str]:
    """Persona skills named in the text."""
    return [s.name for s in facts.skills if any(has_term(text, t) for t in s.terms)]


def gap_hits(text: str, facts: Facts) -> list[str]:
    return [g for g in facts.gaps if has_term(text, g)]


def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in STOPWORDS}


def project_score(text: str, project: Project, facts: Facts) -> int:
    """Shared stack items, persona skills and topic words."""
    stack = [s.lower() for s in project.skills]
    score = sum(has_term(text, s) for s in stack)
    for skill in facts.skills:
        in_text = any(has_term(text, t) for t in skill.terms)
        in_project = any(t in stack for t in skill.terms)
        score += in_text and in_project
    shared = content_words(text) & content_words(f"{project.title} {project.built}")
    return score + min(len(shared), 2)


def ranked_projects(text: str, facts: Facts, limit: int) -> list[tuple[str, int]]:
    scored = [(p.id, project_score(text, p, facts)) for p in facts.projects]
    scored = [x for x in scored if x[1] > 0]
    scored.sort(key=lambda x: (-x[1], x[0]))
    return scored[:limit]
