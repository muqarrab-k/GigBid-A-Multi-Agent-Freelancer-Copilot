import re

from synth.facts import Facts, Project

NUMBER_RE = re.compile(r"\d[\d,.]*%?")


def project_facts(project: Project) -> str:
    """Fact text a proposal may quote, without implied skills."""
    return (f"{project.title} ({project.start} to {project.end}): {project.built} "
            f"Stack: {', '.join(project.stack)}. Results: {'; '.join(project.metrics)}.")


def allowed_text(facts: Facts, cited: list[str], job_title: str, job_text: str) -> str:
    projects = " ".join(project_facts(facts.project(pid)) for pid in cited)
    return f"{projects} {facts.years_experience} years {job_title} {job_text}"


def stray_numbers(text: str, allowed: str) -> list[str]:
    """Numbers (2+ chars) not found in the allowed text, commas ignored."""
    pool = allowed.replace(",", "")
    out = []
    for match in NUMBER_RE.finditer(text):
        number = match.group().rstrip(".,").replace(",", "")
        if len(number) > 1 and number not in pool and number not in out:
            out.append(number)
    return out


def implied_named(text: str, skills: list[str]) -> list[str]:
    lower = text.lower()
    return [s for s in skills if s.lower() in lower]
