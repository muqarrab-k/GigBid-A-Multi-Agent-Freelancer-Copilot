"""Plumbing shared by every bid-graph node."""

import hashlib
import json
import re
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from string import Template
from typing import Any, TypeVar

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import BaseMessage
from langchain_core.runnables import Runnable
from pydantic import BaseModel, ValidationError

from agent.config import ModelSpec, Settings, get_config
from agent.llm import build_chat
from agent.mcp_client import McpLayer
from agent.prompts.loader import load_prompt

T = TypeVar("T", bound=BaseModel)
Chat = Runnable[LanguageModelInput, BaseMessage]
THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def untrusted(text: str, source: str = "job_post") -> str:
    """Delimit stranger-written text with the standard data-only rule."""
    clean = (text or "").replace("</untrusted>", "&lt;/untrusted&gt;")
    return f"{load_prompt('untrusted_rule')}\n<untrusted source=\"{source}\">\n{clean}\n</untrusted>"


def job_text(job: dict[str, Any]) -> str:
    skills = ", ".join(job.get("skills") or [])
    questions = "\n".join(f"- {q}" for q in job.get("screening_questions") or [])
    return (f"Title: {job.get('title', '')}\nSkills: {skills}\n\n{job.get('description') or ''}"
            + (f"\n\nScreening questions:\n{questions}" if questions else ""))


class NodeCache:
    """LLM replies keyed by model and full prompt, so reruns are free."""

    def __init__(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(folder / "llm.sqlite"), check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS replies (key TEXT PRIMARY KEY, reply TEXT)")

    @staticmethod
    def key(model: str, prompt: str) -> str:
        return hashlib.sha256(f"{model}\n{prompt}".encode()).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        row = self.db.execute("SELECT reply FROM replies WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, key: str, reply: dict[str, Any]) -> None:
        self.db.execute("INSERT OR REPLACE INTO replies VALUES (?, ?)", (key, json.dumps(reply)))
        self.db.commit()


@dataclass
class BidContext:
    """Everything nodes need that is not graph state."""

    layer: McpLayer
    persona: str
    settings: Settings = field(default_factory=get_config)
    cache: NodeCache | None = None
    llm: Callable[[ModelSpec], Chat] | None = None

    def chat(self, spec: ModelSpec) -> Chat:
        return self.llm(spec) if self.llm else build_chat(spec, self.settings)

    def store(self) -> NodeCache:
        if self.cache is None:
            self.cache = NodeCache(self.settings.nodes.cache_dir)
        return self.cache


class ToolBox:
    """A node's allowlisted tools, nothing else."""

    def __init__(self, ctx: BidContext, node: str) -> None:
        self.ctx, self.node = ctx, node
        self.allowed = set(ctx.settings.mcp_client.allowlists.get(node, []))
        self.events: list[dict[str, Any]] = []

    async def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name not in self.allowed:
            raise PermissionError(f"{self.node} may not call {name}")
        start = time.perf_counter()
        out = await self.ctx.layer.call(name, args)
        self.events.append({"node": self.node, "kind": "tool",
                            "data": {"tool": name, "args": args, "ok": bool(out.get("ok", True)),
                                     "latency_s": round(time.perf_counter() - start, 3)}})
        return out


def parse_json(text: str) -> Any:
    """First JSON object in a reply, ignoring think blocks and fences."""
    text = THINK_RE.sub("", text).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start : end + 1])


async def ask(ctx: BidContext, spec: ModelSpec, prompt: str) -> tuple[str, dict[str, Any]]:
    """One cached model call; returns text and usage."""
    cache = ctx.store()
    key = cache.key(spec.model, prompt)
    hit = cache.get(key)
    if hit:
        return hit["text"], {**hit["usage"], "cached": True, "latency_s": 0.0}
    start = time.perf_counter()
    reply = await ctx.chat(spec).bind(response_format={"type": "json_object"}).ainvoke(prompt)
    usage = dict(getattr(reply, "usage_metadata", None) or {})
    usage = {"input_tokens": int(usage.get("input_tokens", 0)), "output_tokens": int(usage.get("output_tokens", 0))}
    text = str(reply.content)
    cache.put(key, {"text": text, "usage": usage})
    return text, {**usage, "cached": False, "latency_s": round(time.perf_counter() - start, 2)}


async def structured(ctx: BidContext, node: str, schema: type[T],
                     **values: Any) -> tuple[T | None, list[dict[str, Any]], str | None]:
    """Prompt -> validated model, retry with the error, then the fallback model."""
    spec = ctx.settings.profile.node(node)
    base = Template(load_prompt(node)).substitute(values)
    base += "\n\n" + Template(load_prompt("json_output")).substitute(schema=json.dumps(schema.model_json_schema()))
    models = [spec] * (ctx.settings.nodes.retries + 1) + ([spec.fallback] if spec.fallback else [])
    events, error, prompt = [], None, base
    for i, model in enumerate(models):
        if model is spec.fallback:
            # fresh prompt for the fallback model
            prompt = base
        try:
            text, usage = await ask(ctx, model, prompt)
        except Exception as err:  # noqa: BLE001
            error = f"{model.model}: {type(err).__name__}: {err}"
            events.append(llm_event(node, model, {}, i, False, error))
            continue
        try:
            result = schema.model_validate(parse_json(text))
        except (ValidationError, ValueError) as err:
            error = str(err)[:800]
            events.append(llm_event(node, model, usage, i, False, error))
            prompt = base + "\n\n" + Template(load_prompt("json_retry")).substitute(error=error)
            continue
        events.append(llm_event(node, model, usage, i, True, None))
        return result, events, None
    return None, events, error


def llm_event(node: str, model: ModelSpec, usage: dict[str, Any], attempt: int, ok: bool,
              error: str | None) -> dict[str, Any]:
    tokens_in, tokens_out = usage.get("input_tokens", 0), usage.get("output_tokens", 0)
    usd = (tokens_in * model.usd_per_mtok_in + tokens_out * model.usd_per_mtok_out) / 1e6
    return {"node": node, "kind": "llm", "data": {
        "model": model.model, "attempt": attempt, "ok": ok, "error": error, "cached": usage.get("cached", False),
        "input_tokens": tokens_in, "output_tokens": tokens_out, "latency_s": usage.get("latency_s", 0.0),
        "usd": round(usd, 6)}}


def tokens_used(events: list[dict[str, Any]]) -> int:
    return sum(e["data"].get("input_tokens", 0) + e["data"].get("output_tokens", 0) for e in events if e["kind"] == "llm")
