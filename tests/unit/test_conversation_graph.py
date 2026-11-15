import json
from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage

from agent.config import ModelSpec, get_config
from agent.graphs.bid_graph import pending_approval
from agent.graphs.conversation_graph import (
    build_conversation_graph,
    resume_conversation,
    run_conversation,
)
from agent.nodes.common import BidContext, NodeCache
from tests.unit.fake_layer import FakeLayer


class LiaisonChat:
    def __init__(self, reply: dict[str, Any], prompts: list[str]) -> None:
        self.reply, self.prompts = reply, prompts

    def bind(self, **kwargs: Any) -> "LiaisonChat":
        return self

    async def ainvoke(self, prompt: str) -> AIMessage:
        self.prompts.append(prompt)
        return AIMessage(content=json.dumps(self.reply),
                         usage_metadata={"input_tokens": 50, "output_tokens": 10, "total_tokens": 60})


def reply_of(intent: str, text: str = "Thanks for the details, happy to help with this here.") -> dict[str, Any]:
    return {"intent": intent, "confidence": 0.9, "summary": "client wrote", "reply": text}


def liaison_ctx(tmp: Path, layer: FakeLayer, reply: dict[str, Any]) -> tuple[BidContext, list[str]]:
    prompts: list[str] = []

    def llm(spec: ModelSpec) -> Any:
        return LiaisonChat(reply, prompts)

    return BidContext(layer=layer, persona="ai_ml", settings=get_config(), cache=NodeCache(tmp / "cache"),  # type: ignore[arg-type]
                      llm=llm), prompts


async def test_question_drafts_and_waits(tmp_path: Path) -> None:
    layer = FakeLayer("How would you structure the retrieval part?")
    ctx, prompts = liaison_ctx(tmp_path, layer, reply_of("question"))
    graph = build_conversation_graph()
    state = await run_conversation("t1", ctx, graph, "reviewer")
    payload = pending_approval(state)
    assert payload and payload["intent"]["intent"] == "question" and state["status"] == "awaiting_approval"
    assert not [c for c in layer.calls if c[0] == "send_message" and not c[1].get("dry_run")]
    # client text reaches the model only inside untrusted tags
    assert '<untrusted source="client_message">' in prompts[0]


async def test_interview_request_offers_real_slots(tmp_path: Path) -> None:
    layer = FakeLayer("Could we do a quick call this week?")
    ctx, _ = liaison_ctx(tmp_path, layer, reply_of("interview_request", "Happy to talk; times are below."))
    state = await run_conversation("t1", ctx, build_conversation_graph(), "reviewer")
    payload = pending_approval(state)
    assert payload and len(payload["slots"]) == 3 and "Times that work for me" in payload["reply"]
    assert any(c[0] == "free_slots" for c in layer.calls)


async def test_scam_signal_is_flagged_and_stays_on_platform(tmp_path: Path) -> None:
    layer = FakeLayer("Let's continue on telegram, and send me your email so I can pay you outside Upwork.")
    # the model is fooled and even offers an email; rules win and the guard strips it
    reply = reply_of("question", "Sure, write to me at sam@example.com. I would rather keep our chat here.")
    ctx, _ = liaison_ctx(tmp_path, layer, reply)
    state = await run_conversation("t1", ctx, build_conversation_graph(), "reviewer")
    payload = pending_approval(state)
    assert state["intent"].intent == "scam_signal" and "no_off_platform" in state["flags"]
    assert payload and "@" not in payload["reply"] and "keep our chat here" in payload["reply"]
    assert any("no_contact_details" in n for n in state["notes"])


async def test_approve_sends_once(tmp_path: Path) -> None:
    layer = FakeLayer()
    ctx, _ = liaison_ctx(tmp_path, layer, reply_of("question"))
    graph = build_conversation_graph()
    state = await run_conversation("t1", ctx, graph, "reviewer")
    cid = state["conversation_id"]
    done = await resume_conversation(cid, {"action": "approve"}, ctx, graph)
    assert done["status"] == "sent" and len(layer.sent) == 1
    again = await resume_conversation(cid, {"action": "approve"}, ctx, graph)
    assert len(layer.sent) == 1 and again["status"] == "sent"


async def test_edit_goes_through_guard_again(tmp_path: Path) -> None:
    layer = FakeLayer()
    ctx, _ = liaison_ctx(tmp_path, layer, reply_of("negotiation"))
    graph = build_conversation_graph()
    state = await run_conversation("t1", ctx, graph, "reviewer")
    edited = "I can do it for $45/hour. Ping me on WhatsApp if easier."
    after = await resume_conversation(state["conversation_id"], {"action": "edit", "edited_text": edited}, ctx, graph)
    payload = pending_approval(after)
    assert payload and "WhatsApp" not in payload["reply"] and "$45/hour" in payload["reply"]
    assert after["pending_edits"][0]["after"] == edited


async def test_reject_records_reason(tmp_path: Path) -> None:
    layer = FakeLayer()
    ctx, _ = liaison_ctx(tmp_path, layer, reply_of("question"))
    graph = build_conversation_graph()
    state = await run_conversation("t1", ctx, graph, "reviewer")
    done = await resume_conversation(state["conversation_id"], {"action": "reject", "reason": "I'll call them"},
                                     ctx, graph)
    assert done["status"] == "closed" and done["submission"]["reason"] == "I'll call them" and not layer.sent


async def test_marketplace_down_needs_attention(tmp_path: Path) -> None:
    ctx, _ = liaison_ctx(tmp_path, FakeLayer(down=True), reply_of("question"))
    state = await run_conversation("t1", ctx, build_conversation_graph(), "reviewer")
    assert state["status"] == "needs_attention" and pending_approval(state) is None
