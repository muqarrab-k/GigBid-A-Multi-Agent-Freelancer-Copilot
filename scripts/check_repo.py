"""Repo rules for CI: no committed secrets, no inline prompts outside agent/prompts/."""

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRET_PATTERNS = {
    "openai key": r"sk-(?:proj-)?[A-Za-z0-9_-]{20,}",
    "groq key": r"gsk_[A-Za-z0-9]{20,}",
    "github token": r"gh[pousr]_[A-Za-z0-9]{30,}",
    "hugging face token": r"hf_[A-Za-z0-9]{30,}",
    "aws key": r"AKIA[0-9A-Z]{16}",
    "slack token": r"xox[bpas]-[A-Za-z0-9-]{20,}",
    "private key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "langsmith key": r"lsv2_(?:pt|sk)_[A-Za-z0-9_]{20,}",
}
# words that mark a string as a model prompt
PROMPT_MARKERS = re.compile(r"(?i)\b(you are an?|your task is|respond with|return (only )?json|"
                            r"answer in|as an ai|system prompt)\b")
MIN_PROMPT_CHARS = 160
SKIP_DIRS = ("node_modules/", "apps/web/", "data/", "gigsim/seed/", "evals/datasets/", "evals/cache/")


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if f]


def secrets(files: list[str]) -> list[str]:
    problems = [f"{f}: env file is tracked" for f in files if Path(f).name in (".env", ".env.local")]
    for name in files:
        path = ROOT / name
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if re.search(pattern, text):
                problems.append(f"{name}: looks like a {label}")
    return problems


def docstrings(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def inline_prompts(files: list[str]) -> list[str]:
    problems = []
    for name in files:
        if not name.endswith(".py") or name.startswith(SKIP_DIRS) or "/tests/" in name or name.startswith("tests/"):
            continue
        tree = ast.parse((ROOT / name).read_text())
        skip = docstrings(tree)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip
                    and len(node.value) >= MIN_PROMPT_CHARS and PROMPT_MARKERS.search(node.value)):
                problems.append(f"{name}:{node.lineno}: prompt-like string; move it to agent/prompts/")
    return problems


def main() -> None:
    files = tracked_files()
    problems = secrets(files) + inline_prompts(files)
    for problem in problems:
        print(problem)
    print(f"checked {len(files)} tracked files: {len(problems)} problems")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
