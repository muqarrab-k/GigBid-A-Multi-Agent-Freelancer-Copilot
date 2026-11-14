import hashlib
import json
import time
from collections import Counter
from pathlib import Path
from string import Template
from typing import Any

from openai import RateLimitError

from agent.config import ROOT, ConfigError, Settings, get_config
from agent.llm import build_chat
from agent.prompts.loader import load_prompt

CACHE_DIR = ROOT / "data" / "cache" / "llm"
COST_PATH = ROOT / "evals" / "results" / "synth_cost.json"
MAX_WAITS = 6


class GeneratorUnavailable(RuntimeError):
    """No key or quota for the generator."""


class Generator:
    """Cached LLM calls keyed by prompt hash."""

    def __init__(self, settings: Settings | None = None, cache_dir: Path = CACHE_DIR) -> None:
        self.settings = settings or get_config()
        self.spec = self.settings.models.generator
        self.cache_dir = cache_dir
        self.chat: Any = None
        self.stats: Counter[str] = Counter()
        self.used: set[str] = set()

    def prompt(self, name: str, /, **values: object) -> str:
        return Template(load_prompt(name)).substitute({k: str(v) for k, v in values.items()})

    def key(self, system: str, prompt: str) -> str:
        spec = self.spec
        raw = json.dumps(
            [spec.model, spec.temperature, spec.reasoning_effort, spec.max_tokens, system, prompt]
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def complete(self, name: str, tag: str, /, **values: object) -> str:
        system, prompt = load_prompt("synth_system"), self.prompt(name, **values)
        key = self.key(system, prompt)
        self.used.add(key)
        path = self.cache_dir / f"{key}.json"
        if path.exists():
            self.stats["cache_hits"] += 1
            return str(json.loads(path.read_text())["text"])

        reply = self.call(system, prompt)
        usage = reply.usage_metadata or {}
        record = {
            "model": self.spec.model,
            "prompt_name": name,
            "tag": tag,
            "prompt": prompt,
            "text": str(reply.content).strip(),
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
        }
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=1))
        self.stats["calls"] += 1
        return str(record["text"])

    def call(self, system: str, prompt: str) -> Any:
        if self.chat is None:
            try:
                chat = build_chat(self.spec, self.settings)
            except ConfigError as err:
                raise GeneratorUnavailable(str(err)) from err
            kwargs: dict[str, Any] = {"max_completion_tokens": self.spec.max_tokens}
            if self.spec.reasoning_effort:
                kwargs["reasoning_effort"] = self.spec.reasoning_effort
            self.chat = chat.bind(**kwargs)

        for attempt in range(MAX_WAITS):
            try:
                return self.chat.invoke([("system", system), ("human", prompt)])
            except RateLimitError as err:
                if "per day" in str(err).lower() or attempt == MAX_WAITS - 1:
                    raise GeneratorUnavailable(f"rate limit: {err}") from err
                # back off
                time.sleep(15 * (attempt + 1))
        raise GeneratorUnavailable("rate limit retries exhausted")


def write_cost_report(used: set[str], cache_dir: Path = CACHE_DIR, path: Path = COST_PATH) -> dict[str, Any]:
    """Totals over every cached call, priced from config."""
    spec = get_config().models.generator
    by_tag: dict[str, Counter[str]] = {}
    superseded = 0
    for file in sorted(cache_dir.glob("*.json")):
        record = json.loads(file.read_text())
        superseded += file.stem not in used
        tag = record["tag"]
        counts = by_tag.setdefault(tag, Counter())
        counts["calls"] += 1
        counts["input_tokens"] += record["input_tokens"]
        counts["output_tokens"] += record["output_tokens"]

    total: Counter[str] = Counter()
    for counts in by_tag.values():
        total.update(counts)
    cost = (
        total["input_tokens"] * spec.usd_per_mtok_in + total["output_tokens"] * spec.usd_per_mtok_out
    ) / 1e6
    report = {
        "model": spec.model,
        "provider": spec.provider,
        "prices_usd_per_mtok": {"input": spec.usd_per_mtok_in, "output": spec.usd_per_mtok_out},
        "note": "estimate from token counts and config prices; every paid call counted once",
        "calls": total["calls"],
        "calls_in_corpus": total["calls"] - superseded,
        "superseded_calls": superseded,
        "input_tokens": total["input_tokens"],
        "output_tokens": total["output_tokens"],
        "cost_usd": round(cost, 4),
        "by_tag": {tag: dict(counts) for tag, counts in sorted(by_tag.items())},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2))
    return report
