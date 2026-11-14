import ast
import json
import re
from collections import Counter, defaultdict
from itertools import combinations
from statistics import mean
from typing import Any

import yaml

from agent.config import ROOT
from synth.checks import allowed_text, implied_named, stray_numbers
from synth.facts import PERSONAS, PERSONAS_DIR, Facts, load_facts
from synth.plan import load_jsonl

QUALITY_PATH = ROOT / "evals" / "results" / "synth_quality.json"
GENERIC = ["passionate", "hard-working", "hardworking", "extensive experience", "dedicated",
           "i am confident", "i'm confident"]
CODE_WORDS = re.compile(r"\b(import|export|const|function|def|class|select|from|return|async|model|calculate|sum|divide)\b", re.I)


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def trigram_overlap(a: str, b: str) -> float:
    """Jaccard of word trigrams."""
    ta = {tuple(words(a)[i : i + 3]) for i in range(len(words(a)) - 2)}
    tb = {tuple(words(b)[i : i + 3]) for i in range(len(words(b)) - 2)}
    return len(ta & tb) / max(1, len(ta | tb))


def grounding(facts: Facts, proposals: list[dict[str, Any]]) -> dict[str, Any]:
    """Numbers and client names a proposal may not use."""
    clients = {p.client for p in facts.projects if p.named_client}
    bad_numbers, bad_clients = 0, 0
    examples: list[dict[str, Any]] = []
    for row in proposals:
        text = row["proposal_text"]
        cited = row["cited_projects"]
        stray = stray_numbers(text, allowed_text(facts, cited, row["job_title"], row["job_text"]))
        named = {c for c in clients if c in text} - {facts.project(p).client for p in cited}
        bad_numbers += bool(stray)
        bad_clients += bool(named)
        if (stray or named) and len(examples) < 5:
            examples.append({"evidence_id": row["evidence_id"], "numbers": stray, "clients": sorted(named)})
    return {"proposals": len(proposals), "with_stray_numbers": bad_numbers,
            "naming_uncited_client": bad_clients, "examples": examples}


def texts_by_id(persona: str) -> dict[str, str]:
    """Rendered text per evidence id (no CV)."""
    base = PERSONAS_DIR / persona
    out = {r["evidence_id"]: r["text"] for r in load_jsonl(base / "reviews.jsonl")}
    out |= {r["evidence_id"]: r["proposal_text"] for r in load_jsonl(base / "proposals.jsonl")}
    for row in load_jsonl(base / "manifest.jsonl"):
        if row["type"] in ("case_study", "readme", "code") and (base / row["path"]).exists():
            out[row["evidence_id"]] = (base / row["path"]).read_text()
    return out


def implied_and_duplicates(persona: str, facts: Facts) -> dict[str, Any]:
    """Implied skills named outright, and repeated texts."""
    texts = texts_by_id(persona)
    cited = {r["evidence_id"]: r["cited_projects"]
             for r in load_jsonl(PERSONAS_DIR / persona / "proposals.jsonl")}
    named: Counter[str] = Counter()
    for row in load_jsonl(PERSONAS_DIR / persona / "manifest.jsonl"):
        text = texts.get(row["evidence_id"], "").lower()
        if row["type"] in ("cv", "code") or not text:
            continue
        projects = cited.get(row["evidence_id"]) or ([row["project"]] if row["project"] else [])
        implied = [s for pid in projects for s in facts.project(pid).implied_skills]
        named[row["type"]] += bool(implied_named(text, implied))
    repeats = len(texts) - len(set(texts.values()))
    return {"items_naming_implied_skill": dict(named), "duplicate_texts": repeats}


def three_ways(persona: str, facts: Facts, proposals: list[dict[str, Any]]) -> dict[str, Any]:
    base = PERSONAS_DIR / persona
    scores = []
    for repo in facts.repos:
        project = facts.project(repo.project)
        study = next((base / "case_studies").glob(f"{project.id}-*.md"), None)
        readme = base / "repos" / repo.name / "README.md"
        cites = [r["proposal_text"] for r in proposals if project.id in r["cited_projects"]]
        if not (study and readme.exists() and cites):
            continue
        texts = [study.read_text(), readme.read_text(), cites[0]]
        scores += [trigram_overlap(a, b) for a, b in combinations(texts, 2)]
    return {"pairs": len(scores), "mean_trigram_jaccard": round(mean(scores), 3) if scores else None,
            "max_trigram_jaccard": round(max(scores), 3) if scores else None}


def style(proposals: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in proposals:
        groups[row["outcome"]].append(row)
    out = {}
    for outcome, rows in sorted(groups.items()):
        texts = [r["proposal_text"].lower() for r in rows]
        out[outcome] = {
            "n": len(rows),
            "generic_phrase_rate": round(mean(any(g in t for g in GENERIC) for t in texts), 3),
            "cites_project_rate": round(mean(bool(r["cited_projects"]) for r in rows), 3),
            "mean_words": round(mean(len(t.split()) for t in texts)),
        }
    return out


def code_check(persona: str, facts: Facts) -> dict[str, Any]:
    base = PERSONAS_DIR / persona / "repos"
    checked, python_ok, fenced, prose_like = 0, 0, 0, []
    for repo in facts.repos:
        for file in repo.files:
            path = base / repo.name / file.path
            if not path.exists():
                continue
            text = path.read_text()
            checked += 1
            fenced += text.lstrip().startswith("```")
            if path.suffix == ".py":
                try:
                    ast.parse(text)
                    python_ok += 1
                except SyntaxError:
                    prose_like.append(f"{repo.name}/{file.path} (syntax error)")
            elif path.suffix in (".yml", ".yaml"):
                if not isinstance(yaml.safe_load(text), dict):
                    prose_like.append(f"{repo.name}/{file.path} (not yaml)")
            elif len(CODE_WORDS.findall(text)) < 3:
                prose_like.append(f"{repo.name}/{file.path}")
    py_total = sum(f.path.endswith(".py") for r in facts.repos for f in r.files)
    return {"files": checked, "python_parses": f"{python_ok}/{py_total}", "fenced": fenced,
            "suspect": prose_like}


def main() -> dict[str, Any]:
    report = {}
    for persona in PERSONAS:
        facts = load_facts(persona)
        proposals = load_jsonl(PERSONAS_DIR / persona / "proposals.jsonl")
        report[persona] = {
            "grounding": grounding(facts, proposals),
            "three_ways": three_ways(persona, facts, proposals),
            "style_by_outcome": style(proposals),
            "code": code_check(persona, facts),
            "implied_and_duplicates": implied_and_duplicates(persona, facts),
        }
    QUALITY_PATH.write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    print(json.dumps(main(), indent=1))
