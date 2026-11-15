"""GIGBID_FAKE_LLM=1: scripted model, fake embeddings, in-process GigSim, memory saver and store.

For the web e2e tests and demos without keys. Never used unless the flag is set.
"""

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from langchain_core.messages import AIMessage
from langgraph.store.memory import InMemoryStore
from pydantic import BaseModel

from agent.config import get_config
from agent.graphs.checkpoint import memory_saver
from agent.local_stack import LocalStack
from agent.mcp_client import MarketplaceDown, McpLayer
from agent.nodes.common import NodeCache
from apps.api.core import AppState
from rag.embeddings import FakeEmbedder
from rag.index.store import MemoryStore
from rag.ingest.chunking import FixedChunker
from rag.ingest.documents import Document
from rag.ingest.indexer import IndexStats, index_documents, index_new_work
from rag.ingest.loaders import PersonaLoader
from rag.variants.v0_naive import V0Naive

ANALYST = {"deliverables": ["working prototype"], "requirements": ["Python", "LLM integration", "clear handover"],
           "required_skills": ["Python"], "timeline_days": 14, "screening_questions": [], "hidden_needs": []}
RISK = {"scam_likelihood": 0.1, "flags": [], "injection_seen": False, "red_flags": [], "explanation": "looks fine"}
FIT = {"requirements": ["Python", "LLM integration"]}
LIAISON = {"intent": "interview_request", "confidence": 0.9, "summary": "Client asks for a call.",
           "reply": "Thanks for getting back to me. I am happy to talk through the scope on a short call here."}


def writer_reply(prompt: str) -> str:
    """Only repeats the evidence listed in the prompt, so the verifier passes it."""
    found = re.findall(r"^- \[([a-z_]+:[^\]]+)\] (.+)$", prompt, re.MULTILINE)
    claims = []
    for eid, text in found[:3]:
        words = [w for w in re.findall(r"[a-z]+", text.lower()) if len(w) > 2][:18]
        claims.append(f"I built {' '.join(words)} [{eid}].")
    opening = ("You need a dependable Python and LLM integration that answers from your own data, stays grounded "
               "in your sources and is easy for your team to maintain after handover.")
    closing = ("I would start with a short call to agree the scope, then share a working prototype early so you "
               "can test real questions and steer the next steps before we polish anything.")
    return json.dumps({"paragraphs": [opening, " ".join(claims), closing], "screening_answers": []})


class FakeChat:
    def __init__(self) -> None:
        self.markers = {"Job Analyst": json.dumps(ANALYST), "Risk Assessor": json.dumps(RISK),
                        "Client Liaison": json.dumps(LIAISON), "check sentences": json.dumps({"violations": []}),
                        "check one claim": json.dumps({"label": "supported", "reason": "matches the evidence"})}

    def bind(self, **kwargs: Any) -> "FakeChat":
        return self

    async def ainvoke(self, prompt: str) -> AIMessage:
        reply = next((r for m, r in self.markers.items() if m in prompt), None)
        if reply is None:
            reply = writer_reply(prompt) if "Proposal Writer" in prompt else json.dumps(FIT)
        return AIMessage(content=reply, usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120})


class Toggle:
    down = False


class ToggleLayer:
    """Wraps a real layer; /test/marketplace makes the marketplace look down."""

    def __init__(self, layer: McpLayer) -> None:
        self.layer, self.user = layer, layer.user

    async def server_status(self) -> dict[str, str]:
        return await self.layer.server_status()

    async def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        server = self.layer.tools[name][0]
        if Toggle.down and server == "marketplace":
            return MarketplaceDown(server="marketplace", detail="test mode outage").model_dump()
        return await self.layer.call(name, args)


def build_test_state() -> AppState:
    settings = get_config()
    folder = Path(tempfile.mkdtemp(prefix="gigbid-test-"))
    # fake embeddings score low; let every hit count
    settings = settings.model_copy(update={
        "thresholds": settings.thresholds.model_copy(update={"minimum_fit_score": 0.0, "watch_fit_score": 0.0}),
        "fit": settings.fit.model_copy(update={"strong_score": -1.0, "partial_score": -1.0}),
        "scout": settings.scout.model_copy(update={"seen_store": folder / "seen.sqlite"})})
    store, embedder = MemoryStore(), FakeEmbedder(128)
    for persona in ("ai_ml", "fullstack", "data_analyst"):
        index_documents(PersonaLoader(persona).load(), persona, store, embedder, FixedChunker(200, 40))
    stack = LocalStack(folder, retriever=V0Naive(store, embedder))

    async def layers(user: str) -> Any:
        layer = stack.layer(user)
        await layer.discover()
        return ToggleLayer(layer)

    def indexer(docs: list[Document], persona: str) -> IndexStats:
        return index_new_work(docs, persona, store, embedder, FixedChunker(200, 40))

    return AppState(settings=settings, saver=memory_saver(), store=InMemoryStore(), layer_factory=layers,
                    llm=lambda spec: FakeChat(), cache=NodeCache(folder / "cache"), indexer=indexer)  # type: ignore[arg-type,return-value]


class MarketplaceIn(BaseModel):
    down: bool


router = APIRouter(prefix="/test", tags=["test"])


@router.post("/marketplace")
async def set_marketplace(body: MarketplaceIn) -> dict[str, bool]:
    Toggle.down = body.down
    return {"down": Toggle.down}

