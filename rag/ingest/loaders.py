import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from pypdf import PdfReader

from agent.config import ROOT
from rag.ingest.documents import Document

PERSONAS_DIR = ROOT / "data" / "personas"
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".sql", ".dax", ".yml", ".yaml", ".prisma", ".go", ".rs", ".java"}
LANGUAGES = {".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript", ".sql": "SQL",
             ".dax": "DAX", ".prisma": "Prisma", ".go": "Go", ".rs": "Rust", ".java": "Java"}


class Loader(Protocol):
    def load(self) -> list[Document]: ...


def pdf_text(path: Path) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages).strip()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class PersonaLoader:
    """A synthetic persona folder, driven by its manifest.jsonl."""

    def __init__(self, persona: str, root: Path = PERSONAS_DIR) -> None:
        self.persona = persona
        self.base = root / persona

    def load(self) -> list[Document]:
        rows = {r["evidence_id"]: r for name in ("reviews.jsonl", "proposals.jsonl")
                for r in read_jsonl(self.base / name)}
        docs = []
        for item in read_jsonl(self.base / "manifest.jsonl"):
            if not item.get("rendered", True):
                continue
            text, source, extra = self.text_for(item, rows.get(item["evidence_id"], {}))
            if not text.strip():
                continue
            docs.append(Document(
                evidence_id=item["evidence_id"], persona=self.persona, type=item["type"], text=text,
                project=item.get("project"), skills=item.get("skills") or [], date=item.get("date"),
                client_industry=item.get("client_industry"), outcome=item.get("outcome"),
                source_path=source, extra=extra,
            ))
        return docs

    def text_for(self, item: dict[str, Any], row: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
        path = f"data/personas/{self.persona}/{item['path']}"
        if item["type"] == "cv":
            return pdf_text(self.base / item["path"]), path, {}
        if item["type"] == "review":
            return row.get("text", ""), f"{path}#{item['evidence_id']}", {"rating": row.get("rating")}
        if item["type"] == "proposal":
            extra = {"job_id": row.get("job_id"), "job_title": row.get("job_title"),
                     "cited_projects": row.get("cited_projects", [])}
            return row.get("proposal_text", ""), f"{path}#{item['evidence_id']}", extra
        return (self.base / item["path"]).read_text(), path, {}


class FolderLoader:
    """Any folder of md, pdf and code, with simple metadata guesses."""

    def __init__(self, folder: Path, persona: str = "local") -> None:
        self.folder, self.persona = folder, persona

    def guess_type(self, path: Path) -> str:
        if path.suffix == ".pdf":
            return "cv" if "cv" in path.stem.lower() or "resume" in path.stem.lower() else "document"
        if path.name.lower() == "readme.md":
            return "readme"
        return "code" if path.suffix in CODE_SUFFIXES else "case_study"

    def load(self) -> list[Document]:
        docs = []
        for path in sorted(self.folder.rglob("*")):
            if not path.is_file() or path.suffix not in {".md", ".pdf", *CODE_SUFFIXES}:
                continue
            if any(part.startswith(".") for part in path.relative_to(self.folder).parts):
                continue
            rel = path.relative_to(self.folder)
            text = pdf_text(path) if path.suffix == ".pdf" else path.read_text(errors="ignore")
            if not text.strip():
                continue
            skills = [LANGUAGES[path.suffix]] if path.suffix in LANGUAGES else []
            skills += re.findall(r"`([A-Za-z][\w.+-]{1,30})`", text)[:5]
            docs.append(Document(
                evidence_id=f"{self.persona}:{rel.as_posix()}", persona=self.persona, type=self.guess_type(path),
                text=text, project=rel.parts[0] if len(rel.parts) > 1 else None,
                skills=sorted(set(skills)), source_path=str(path),
                date=datetime.fromtimestamp(path.stat().st_mtime, UTC).date().isoformat(),
            ))
        return docs


def persona_names(root: Path = PERSONAS_DIR) -> list[str]:
    return sorted(p.name for p in root.iterdir() if (p / "manifest.jsonl").exists())
