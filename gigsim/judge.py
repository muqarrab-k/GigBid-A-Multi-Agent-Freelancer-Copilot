import hashlib
import json
import os
import re
from pathlib import Path
from string import Template
from typing import Any

from openai import OpenAI

from gigsim.seeding import load_templates
from gigsim.settings import LLMJudge


class Judge:
    """Optional LLM reply-likelihood, temperature 0, cached."""

    def __init__(self, cfg: LLMJudge, cache_dir: Path) -> None:
        self.cfg = cfg
        self.cache_dir = cache_dir
        self.client: Any = None

    @property
    def available(self) -> bool:
        return bool(os.getenv(self.cfg.api_key_env))

    def score(self, proposal: dict[str, Any], job: dict[str, Any], secret: dict[str, Any]) -> float | None:
        """Score in rule units (about -2..2), or None."""
        prompt = Template(load_templates()["judge_prompt"]).substitute(
            must=", ".join(secret["must_have_skills"]) or "none",
            dislikes=", ".join(secret["dislikes"]) or "nothing",
            ceiling=secret.get("budget_ceiling_fixed") or secret.get("budget_ceiling_hourly") or "unknown",
            title=job.get("title", ""),
            proposal=proposal["cover_letter"],
        )
        key = hashlib.sha256(f"{self.cfg.model}|{prompt}".encode()).hexdigest()
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            text = json.loads(path.read_text())["text"]
        elif self.available:
            text = self.ask(prompt)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"model": self.cfg.model, "text": text}))
        else:
            return None
        match = re.search(r"\d+", text)
        return (min(int(match.group()), 10) - 5) / 2.5 if match else None

    def ask(self, prompt: str) -> str:
        if self.client is None:
            self.client = OpenAI(api_key=os.environ[self.cfg.api_key_env], base_url=self.cfg.base_url)
        reply = self.client.chat.completions.create(
            model=self.cfg.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_completion_tokens=5,
        )
        return str(reply.choices[0].message.content or "")
