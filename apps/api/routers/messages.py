"""Client threads, conversation-graph drafts; approvals go through /approvals."""

from typing import Any

from fastapi import APIRouter, HTTPException

from agent.graphs.conversation_graph import conversation_id, run_conversation
from agent.nodes.common import ToolBox
from apps.api.core import new_trace
from apps.api.deps import State, User
from apps.api.schemas import DraftOut, MessageRow, ThreadDetail, ThreadRow, ThreadsOut

router = APIRouter(prefix="/messages", tags=["messages"])


async def tools(state: State, user: User) -> ToolBox:
    return ToolBox(await state.context(user), "client_liaison")


def message_row(m: dict[str, Any]) -> MessageRow:
    wrapped = m.get("untrusted_text")
    text = wrapped["text"] if isinstance(wrapped, dict) else m.get("text") or ""
    return MessageRow(message_id=m["message_id"], sender=m["sender"], text=text, sent_at=m.get("created_at"),
                      untrusted=m["sender"] == "client")


@router.get("", response_model=ThreadsOut)
async def threads(state: State, user: User) -> ThreadsOut:
    out = await (await tools(state, user)).call("list_threads", {})
    if out.get("error") == "marketplace_down":
        raise HTTPException(503, "marketplace unavailable")
    rows = []
    for t in out.get("items", []):
        cid = conversation_id(user["username"], t["thread_id"])
        known = await state.thread(user["username"], cid)
        status = (await state.snapshot("conversation", cid)).values.get("status") if known else None
        rows.append(ThreadRow(thread_id=t["thread_id"], proposal_id=t.get("proposal_id"), job_id=t.get("job_id"),
                              conversation_id=cid, draft_status=status))
    return ThreadsOut(items=rows)


@router.get("/{thread_id}", response_model=ThreadDetail)
async def thread(thread_id: str, state: State, user: User) -> ThreadDetail:
    out = await (await tools(state, user)).call("list_messages", {"thread_id": thread_id})
    if not out.get("ok", True):
        raise HTTPException(503 if out.get("error") == "marketplace_down" else 404, str(out.get("error")))
    cid = conversation_id(user["username"], thread_id)
    known = await state.thread(user["username"], cid)
    values = (await state.snapshot("conversation", cid)).values if known else {}
    intent = values.get("intent")
    return ThreadDetail(thread_id=thread_id, conversation_id=cid, messages=[message_row(m) for m in out["items"]],
                        intent=intent.intent if intent else None, flags=values.get("flags", []),
                        draft_status=values.get("status"),
                        pending=await state.pending("conversation", cid) if known else None)


@router.post("/{thread_id}/draft", response_model=DraftOut)
async def draft(thread_id: str, state: State, user: User, job_title: str | None = None) -> DraftOut:
    """Run the conversation graph up to the approval interrupt."""
    cid = conversation_id(user["username"], thread_id)
    if await state.thread(user["username"], cid) and await state.pending("conversation", cid):
        raise HTTPException(409, "a draft is already waiting for approval")
    known = await state.thread(user["username"], cid)
    await state.register(user["username"], cid, "conversation", marketplace_thread=thread_id,
                         trace_id=(known or {}).get("trace_id") or new_trace())
    result = await run_conversation(thread_id, await state.context(user), state.conv_graph, user["username"],
                                    job_title)
    intent = result.get("intent")
    return DraftOut(conversation_id=cid, status=result.get("status"), intent=intent.intent if intent else None,
                    flags=result.get("flags", []), pending=await state.pending("conversation", cid),
                    errors=result.get("errors", []))
