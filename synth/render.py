import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

from synth.facts import PERSONAS_DIR, Facts, load_facts
from synth.generator import Generator, GeneratorUnavailable
from synth.plan import Item, plan_persona

NUMBER_RE = re.compile(r"\d[\d,.]*%?")
CV_PROJECTS = 10


def cv_markdown(facts: Facts) -> str:
    """Structured CV straight from facts."""
    lines = [
        f"# {facts.name}",
        f"{facts.headline}",
        f"{facts.location} ({facts.timezone}) | {', '.join(facts.languages)}",
        "SYNTHETIC persona for testing; not a real person.",
        "",
        "## Skills",
    ]
    for level in ("expert", "proficient", "familiar"):
        names = [s.name for s in facts.skills if s.level == level]
        if names:
            lines.append(f"- {level.title()}: {', '.join(names)}")
    lines += ["", "## Selected projects"]
    recent = sorted(facts.projects, key=lambda p: p.end, reverse=True)[:CV_PROJECTS]
    for project in recent:
        client = project.client if project.named_client else f"Confidential {project.client_industry} client"
        lines.append(f"- {project.start} to {project.end}, {client}: {project.built} {project.metrics[0]}.")
    lines += ["", "## Education", f"- {facts.education}"]
    return "\n".join(lines) + "\n"


def write_pdf(markdown: str, path: Path) -> None:
    styles = getSampleStyleSheet()
    story: list[Any] = []
    bullets: list[ListItem] = []

    def flush() -> None:
        if bullets:
            story.append(ListFlowable(list(bullets), bulletType="bullet"))
            bullets.clear()

    for line in markdown.splitlines():
        text = line.replace("&", "&amp;").replace("<", "&lt;")
        if line.startswith("- "):
            bullets.append(ListItem(Paragraph(text[2:], styles["BodyText"])))
            continue
        flush()
        if line.startswith("# "):
            story.append(Paragraph(text[2:], styles["Title"]))
        elif line.startswith("## "):
            story.append(Paragraph(text[3:], styles["Heading2"]))
        elif line.strip():
            story.append(Paragraph(text, styles["BodyText"]))
        else:
            story.append(Spacer(1, 6))
    flush()
    # fixed metadata
    doc = SimpleDocTemplate(str(path), pagesize=A4, title="CV", author="synthetic", invariant=1)
    doc.build(story)


def numbers_outside_facts(text: str, item: Item, facts: Facts) -> list[str]:
    """Numbers in a proposal not found in the cited facts."""
    allowed = " ".join(
        f"{facts.project(pid).built} {' '.join(facts.project(pid).metrics)}"
        for pid in item.extra.get("cited_projects", [])
    )
    allowed += f" {facts.years_experience}"
    return [n for n in NUMBER_RE.findall(text) if n.rstrip(".,") not in allowed and len(n) > 1]


class Renderer:
    def __init__(self, generator: Generator, root: Path = PERSONAS_DIR) -> None:
        self.generator = generator
        self.root = root
        self.stopped: str | None = None
        self.checks: Counter[str] = Counter()

    def text_for(self, item: Item) -> str | None:
        if self.stopped or item.prompt is None:
            return None
        try:
            return self.generator.complete(item.prompt, item.tag, **item.values)
        except GeneratorUnavailable as err:
            self.stopped = str(err)
            return None

    def check(self, item: Item, text: str, facts: Facts) -> None:
        if item.project:
            implied = facts.project(item.project).implied_skills
            if item.type != "code" and any(s.lower() in text.lower() for s in implied):
                self.checks["implied_skill_named"] += 1
        if item.type == "proposal" and numbers_outside_facts(text, item, facts):
            self.checks["proposal_numbers_outside_facts"] += 1

    def render_persona(self, persona: str) -> dict[str, Any]:
        facts = load_facts(persona, self.root)
        base = self.root / persona
        items = plan_persona(persona, self.root)
        rendered: dict[str, bool] = {}
        reviews, proposals = [], []

        markdown = cv_markdown(facts)
        (base / "cv.md").write_text(markdown)
        write_pdf(markdown, base / "cv.pdf")

        for item in items:
            if item.type == "cv":
                rendered[item.evidence_id] = True
                continue
            text = self.text_for(item)
            rendered[item.evidence_id] = text is not None
            if text is None:
                continue
            self.check(item, text, facts)
            if item.type == "review":
                reviews.append(review_row(item, text))
            elif item.type == "proposal":
                proposals.append(proposal_row(item, text))
            else:
                out = base / item.path
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(text.rstrip() + "\n")

        write_jsonl(base / "reviews.jsonl", reviews)
        write_jsonl(base / "proposals.jsonl", proposals)
        write_jsonl(base / "manifest.jsonl", [i.manifest_row(rendered[i.evidence_id]) for i in items])
        return {"items": len(items), "rendered": sum(rendered.values()), "types": Counter(i.type for i in items)}


def review_row(item: Item, text: str) -> dict[str, Any]:
    return {"evidence_id": item.evidence_id, "project": item.project, "date": item.date,
            "client": item.extra["client"], "rating": item.extra["rating"], "text": text,
            "synthetic": True}


def proposal_row(item: Item, text: str) -> dict[str, Any]:
    extra = item.extra
    return {"evidence_id": item.evidence_id, "date": item.date, "job_id": extra["job_id"],
            "job_title": extra["job_title"], "job_text": extra["job_text"],
            "job_source": "REAL post from gigsim/seed/real/jobs_history.jsonl",
            "proposal_text": text, "cited_projects": extra["cited_projects"],
            "outcome": item.outcome, "synthetic": True}


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
