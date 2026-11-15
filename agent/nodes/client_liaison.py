"""Client Liaison: read new messages, classify intent, draft a reply or slots, guard it, wait for a human."""

import hashlib
import re
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from operator import add
from pathlib import Path
from typing import Annotated, Any

import yaml
from langgraph.runtime import Runtime
from langgraph.types import interrupt
from pydantic import BaseModel, Field

from agent.config import get_config
from agent.handoffs import Approval, ClientIntent, IntentLabel, InterviewSlot
from agent.nodes.common import BidContext, ToolBox, structured, tokens_used, untrusted
from agent.nodes.compliance import rule_hits
from agent.profile import load_profile
from agent.state import ConversationState, ThreadMessage
from rag.verify import sentences

NODE = "client_liaison"
# client text is checked against these, the reply against the message rules
SCAM_RULES = {"no_off_platform", "no_unpaid_work", "no_credentials_or_crypto", "no_upfront_fees", "no_contact_details"}
REPLY_SKIP = {"no_fabrication", "untrusted_input"}
SLOT_COUNT = 3
SLOT_MINUTES = 30
SLOT_DAYS = 7


class LiaisonOut(BaseModel):
    intent: IntentLabel
    confidence: float = Field(ge=0, le=1)
    summary: str = ""
    reply: str = Field(min_length=1, max_length=2000)


class LiaisonState(ConversationState, total=False):
    conversation_id: str
    persona: str
    job_title: str
    flags: list[str]
    approval_preview: dict[str, Any]
    submission: dict[str, Any]
    notes: Annotated[list[str], add]
    pending_edits: Annotated[list[dict[str, Any]], add]


@lru_cache(maxsize=2)
def message_rules(path: Path) -> list[dict[str, Any]]:
    rules: list[dict[str, Any]] = yaml.safe_load(path.read_text())["rules"]
    return [r for r in rules if "message" in r.get("applies_to", [])]


def client_text(item: dict[str, Any]) -> str:
    wrapped = item.get("untrusted_text")
    return wrapped["text"] if isinstance(wrapped, dict) else str(item.get("text") or "")


def last_client(state: LiaisonState) -> ThreadMessage | None:
    return next((m for m in reversed(state.get("messages", [])) if m["sender"] == "client"), None)


def rule_flags(text: str, ctx: BidContext) -> list[str]:
    """Deterministic scam and injection signals; the model cannot argue these away."""
    rules = message_rules(ctx.settings.compliance.policy_rules_path)
    flags = [r["id"] for r in rules if r["id"] in SCAM_RULES and rule_hits(text, r)]
    flags += [f"pattern:{p.flag}" for p in ctx.settings.risk.patterns if re.search(p.regex, text)]
    if any(re.search(p, text) for p in ctx.settings.risk.injection_patterns):
        flags.append("injection")
    return list(dict.fromkeys(flags))


def scam_flags(flags: list[str]) -> bool:
    return any(f != "injection" for f in flags)


async def read_messages(state: LiaisonState, runtime: Runtime[BidContext]) -> dict[str, Any]:
    tools = ToolBox(runtime.context, NODE)
    out = await tools.call("list_messages", {"thread_id": state["thread_id"]})
    if not out.get("ok", True) or "items" not in out:
        return {"status": "needs_attention", "trace": tools.events, "step_count": 1,
                "errors": [f"list_messages: {out.get('error')} (queued, try again later)"]}
    messages: list[ThreadMessage] = [{"message_id": m["message_id"], "sender": m["sender"], "text": client_text(m),
                                      "sent_at": m.get("created_at") or ""} for m in out["items"]]
    return {"messages": messages, "status": "drafting", "trace": tools.events, "step_count": 1}


def after_read(state: LiaisonState) -> str:
    if state.get("status") == "needs_attention":
        return "end"
    return "classify" if last_client(state) else "end"


async def classify(state: LiaisonState, runtime: Runtime[BidContext]) -> dict[str, Any]:
    ctx = runtime.context
    latest = last_client(state)
    assert latest is not None
    flags = rule_flags(latest["text"], ctx)
    history = "\n".join(f"{m['sender']}: " + (untrusted(m["text"], "client_message") if m["sender"] == "client"
                                               else m["text"]) for m in state.get("messages", [])[-8:])
    profile = load_profile(ctx.persona)
    out, events, error = await structured(ctx, NODE, LiaisonOut, name=profile.name,
                                          job_title=state.get("job_title") or "(unknown)", history=history,
                                          floor=f"${profile.hourly_floor:.0f}/hour")
    update: dict[str, Any] = {"trace": events, "token_count": tokens_used(events), "step_count": 1, "flags": flags}
    if out is None:
        return {**update, "status": "needs_attention", "errors": [f"client_liaison: {error}"]}
    label = "scam_signal" if scam_flags(flags) else out.intent
    intent = ClientIntent(intent=label, confidence=1.0 if label != out.intent else out.confidence,
                          summary=out.summary[:300])
    notes = [f"rules overrode the model ({out.intent} -> scam_signal): {flags}"] if label != out.intent else []
    return {**update, "intent": intent, "draft_reply": out.reply, "notes": notes}


def after_classify(state: LiaisonState) -> str:
    if state.get("status") == "needs_attention":
        return "end"
    return "propose_slots" if state["intent"].intent == "interview_request" else "guard"


def timezone_of(ctx: BidContext) -> str:
    return get_config().mcp.user(ctx.layer.user).timezone


def slot_line(slot: InterviewSlot) -> str:
    return f"- {slot.start:%a %d %b, %H:%M} to {slot.end:%H:%M}"


async def propose_slots(state: LiaisonState, runtime: Runtime[BidContext]) -> dict[str, Any]:
    """Real free time from the workspace calendar, appended to the reply."""
    ctx = runtime.context
    latest = last_client(state)
    sent = (latest["sent_at"] if latest else "") or datetime.now(UTC).isoformat()
    day = datetime.fromisoformat(sent.replace("Z", "+00:00")).replace(hour=0, minute=0, second=0, microsecond=0)
    tz = timezone_of(ctx)
    tools = ToolBox(ctx, NODE)
    out = await tools.call("free_slots", {"start": (day + timedelta(days=1)).isoformat(),
                                          "end": (day + timedelta(days=SLOT_DAYS)).isoformat(),
                                          "duration_minutes": SLOT_MINUTES, "timezone": tz, "limit": SLOT_COUNT})
    slots = [InterviewSlot.model_validate(s) for s in out.get("slots", [])][:SLOT_COUNT]
    if not slots:
        return {"trace": tools.events, "step_count": 1, "proposed_slots": [],
                "notes": ["no free slots found; ask the human to suggest times"]}
    reply = f"{state['draft_reply'].rstrip()}\n\nTimes that work for me ({tz}):\n" + "\n".join(map(slot_line, slots))
    return {"trace": tools.events, "step_count": 1, "proposed_slots": slots, "draft_reply": reply}


def guard(state: LiaisonState, runtime: Runtime[BidContext]) -> dict[str, Any]:
    """Message rules on the outgoing reply: drop what breaks them."""
    ctx = runtime.context
    rules = [r for r in message_rules(ctx.settings.compliance.policy_rules_path) if r["id"] not in REPLY_SKIP]
    kept, notes = [], []
    for para in state.get("draft_reply", "").split("\n\n"):
        lines = []
        for line in para.split("\n"):
            parts = sentences(line) if not line.startswith("- ") else [line]
            ok = []
            for part in parts:
                broken = [r["id"] for r in rules if rule_hits(part, r)]
                if broken:
                    notes.append(f"removed ({', '.join(broken)}): {part[:120]}")
                else:
                    ok.append(part)
            if ok:
                lines.append(" ".join(ok))
        if lines:
            kept.append("\n".join(lines))
    reply = "\n\n".join(kept)
    if not reply.strip():
        return {"status": "needs_attention", "step_count": 1, "notes": notes,
                "errors": ["every sentence of the reply broke a message rule; nothing to send"]}
    return {"draft_reply": reply, "notes": notes, "step_count": 1}


def after_guard(state: LiaisonState) -> str:
    return "end" if state.get("status") == "needs_attention" else "prepare_reply"


async def prepare_reply(state: LiaisonState, runtime: Runtime[BidContext]) -> dict[str, Any]:
    tools = ToolBox(runtime.context, NODE)
    preview = await tools.call("send_message", {"thread_id": state["thread_id"], "text": state["draft_reply"],
                                                "idempotency_key": idempotency_key(state), "dry_run": True})
    if preview.get("error") == "marketplace_down":
        return {"status": "needs_attention", "trace": tools.events, "step_count": 1,
                "errors": ["marketplace unavailable before approval; queued"]}
    check = preview.get("policy_check") or {}
    if check.get("passed") is False:
        return {"status": "needs_attention", "trace": tools.events, "step_count": 1,
                "errors": [f"marketplace policy check failed: {check.get('rule_id')} {check.get('detail', '')}".strip()]}
    latest = last_client(state)
    payload = {"kind": "conversation", "thread_id": state["thread_id"], "conversation_id": state["conversation_id"],
               "intent": state["intent"].model_dump(), "flags": state.get("flags", []),
               "client_message": latest["text"] if latest else "", "reply": state["draft_reply"],
               "slots": [s.model_dump(mode="json") for s in state.get("proposed_slots", [])],
               "preview": {"send_message": {"dry_run": True, "policy_check": preview.get("policy_check")}},
               "notes": state.get("notes", [])}
    return {"approval_preview": payload, "status": "awaiting_approval", "trace": tools.events, "step_count": 1}


def approval_gate(state: LiaisonState) -> dict[str, Any]:
    answer = interrupt(state["approval_preview"])
    approval = answer if isinstance(answer, Approval) else Approval.model_validate(answer)
    return {"approval": approval, "step_count": 1,
            "trace": [{"node": "approval_gate", "kind": "human", "data": approval.model_dump()}]}


def after_gate(state: LiaisonState) -> str:
    return {"approve": "send", "edit": "apply_edit", "reject": "reject"}[state["approval"].action]


def apply_edit(state: LiaisonState) -> dict[str, Any]:
    new = state["approval"].edited_text or ""
    return {"draft_reply": new, "status": "drafting", "step_count": 1,
            "pending_edits": [{"thread_id": state["conversation_id"], "kind": "message",
                               "before": state["draft_reply"], "after": new}]}


def reject(state: LiaisonState) -> dict[str, Any]:
    return {"status": "closed", "step_count": 1,
            "submission": {"outcome": "rejected", "reason": state["approval"].reason or "no reason given"}}


def idempotency_key(state: LiaisonState) -> str:
    digest = hashlib.sha256(state["draft_reply"].encode()).hexdigest()[:16]
    return f"{state['conversation_id']}:{digest}"


async def send(state: LiaisonState, runtime: Runtime[BidContext]) -> dict[str, Any]:
    """Only after an approve; the key makes a resumed send safe."""
    if state.get("approval") is None or state["approval"].action != "approve":
        raise PermissionError("send_message needs a human approval")
    tools = ToolBox(runtime.context, NODE)
    key = idempotency_key(state)
    out = await tools.call("send_message", {"thread_id": state["thread_id"], "text": state["draft_reply"],
                                            "idempotency_key": key})
    if not out.get("ok", True) or not out.get("message"):
        return {"status": "needs_attention", "trace": tools.events, "step_count": 1,
                "errors": [f"send_message: {out.get('error')} {out.get('detail', '')}".strip()]}
    return {"status": "sent", "trace": tools.events, "step_count": 1,
            "submission": {"message_id": out["message"]["message_id"], "idempotency_key": key}}
