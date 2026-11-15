import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

TEXT_SUFFIXES = {".md", ".txt", ".py", ".ts", ".tsx", ".js", ".sql", ".dax", ".yml", ".yaml", ".prisma"}
CODE_SUFFIXES = TEXT_SUFFIXES - {".md", ".txt"}
WORD_RE = re.compile(r"[a-z0-9][a-z0-9+#.]*")
CHUNK_WORDS = 180


@dataclass
class Doc:
    evidence_id: str
    type: str
    source: str
    text: str
    project: str | None = None
    date: str | None = None
    outcome: str | None = None
    client_industry: str | None = None
    skills: list[str] = field(default_factory=list)


@dataclass
class Hit:
    doc: Doc
    score: float
    snippet: str


def guess_type(rel: Path) -> str:
    name, parts = rel.name.lower(), [p.lower() for p in rel.parts]
    if "case_studies" in parts or "case-studies" in parts:
        return "case_study"
    if name.startswith("readme"):
        return "readme"
    if name.startswith("cv") or name.startswith("resume"):
        return "cv"
    if rel.suffix.lower() in CODE_SUFFIXES:
        return "code"
    return "document"


def load_manifest(folder: Path) -> dict[str, dict[str, object]]:
    """Optional manifest.jsonl rows by path or evidence id."""
    path = folder / "manifest.jsonl"
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {str(r.get("path")): r for r in rows} | {str(r["evidence_id"]): r for r in rows}


def from_meta(doc: Doc, meta: dict[str, object] | None) -> Doc:
    if meta:
        doc.evidence_id = str(meta.get("evidence_id") or doc.evidence_id)
        doc.type = str(meta.get("type") or doc.type)
        doc.project = meta.get("project") or doc.project  # type: ignore[assignment]
        doc.date = meta.get("date") or doc.date  # type: ignore[assignment]
        doc.outcome = meta.get("outcome") or doc.outcome  # type: ignore[assignment]
        doc.client_industry = meta.get("client_industry") or doc.client_industry  # type: ignore[assignment]
        doc.skills = list(meta.get("skills") or doc.skills)  # type: ignore[call-overload]
    return doc


def load_jsonl_docs(path: Path, rel: Path, manifest: dict[str, dict[str, object]]) -> list[Doc]:
    """reviews.jsonl / proposals.jsonl style files, one item per line."""
    kind = "proposal" if "proposal" in path.name else "review" if "review" in path.name else "document"
    docs = []
    for n, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        text = row.get("text") or row.get("proposal_text") or ""
        if row.get("job_title"):
            text = f"Job: {row['job_title']}\n\n{text}"
        doc = Doc(evidence_id=row.get("evidence_id") or f"{rel}:{n}", type=kind, source=str(rel),
                  text=text, project=row.get("project"), date=row.get("date"), outcome=row.get("outcome"))
        docs.append(from_meta(doc, manifest.get(doc.evidence_id)))
    return docs


def load_folder(folder: Path) -> list[Doc]:
    """Every text file in the folder becomes evidence."""
    manifest = load_manifest(folder)
    docs: list[Doc] = []
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder)
        if not path.is_file() or any(p.startswith(".") for p in rel.parts) or path.name == "manifest.jsonl":
            continue
        if path.suffix == ".jsonl":
            docs += load_jsonl_docs(path, rel, manifest)
        elif path.suffix.lower() in TEXT_SUFFIXES:
            doc = Doc(evidence_id=str(rel), type=guess_type(rel), source=str(rel),
                      text=path.read_text(errors="ignore"))
            docs.append(from_meta(doc, manifest.get(str(rel))))
    return docs


def words(text: str) -> list[str]:
    return [w.rstrip(".") for w in WORD_RE.findall(text.lower())]


def chunks(text: str) -> list[str]:
    """Paragraphs merged up to about CHUNK_WORDS words."""
    out, current = [], ""
    for para in re.split(r"\n\s*\n", text):
        if current and len((current + para).split()) > CHUNK_WORDS:
            out.append(current)
            current = ""
        current = f"{current}\n\n{para}".strip()
    return [*out, current] if current else out


class Bm25:
    """Plain Okapi BM25 over chunks."""

    def __init__(self, docs: list[Doc], k1: float = 1.5, b: float = 0.75) -> None:
        self.rows = [(doc, chunk, Counter(words(chunk))) for doc in docs for chunk in chunks(doc.text)]
        self.k1, self.b = k1, b
        self.avg = sum(sum(c.values()) for _, _, c in self.rows) / max(1, len(self.rows))
        df: Counter[str] = Counter()
        for _, _, counts in self.rows:
            df.update(counts.keys())
        n = len(self.rows)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, query: list[str], counts: Counter[str]) -> float:
        length = sum(counts.values())
        total = 0.0
        for term in query:
            tf = counts.get(term, 0)
            if tf:
                norm = tf + self.k1 * (1 - self.b + self.b * length / self.avg)
                total += self.idf.get(term, 0.0) * tf * (self.k1 + 1) / norm
        return total

    def search(self, query: str, k: int, types: set[str]) -> list[Hit]:
        terms = words(query)
        best: dict[str, Hit] = {}
        for doc, chunk, counts in self.rows:
            if doc.type not in types:
                continue
            score = self.score(terms, counts)
            if score > 0 and (doc.evidence_id not in best or score > best[doc.evidence_id].score):
                best[doc.evidence_id] = Hit(doc, round(score, 4), chunk[:600])
        return sorted(best.values(), key=lambda h: -h.score)[:k]
