"""Pending approvals from the checkpointer; approve, edit or reject resumes the thread."""

from fastapi import APIRouter, HTTPException
from langgraph.types import Command
from pydantic import ValidationError

from agent.graphs.bid_graph import invoke
from agent.handoffs import Approval
from apps.api.deps import State, User
from apps.api.schemas import ApprovalIn, ApprovalItem, ApprovalResult, ApprovalsOut

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=ApprovalsOut)
async def pending(state: State, user: User) -> ApprovalsOut:
    """Read from saved checkpoints, so a page refresh or a restart never loses one."""
    items = []
    for t in await state.threads(user["username"]):
        payload = await state.pending(t["kind"], t["thread_id"])
        if payload is not None:
            items.append(ApprovalItem(thread_id=t["thread_id"], kind=t["kind"], payload=payload))
    return ApprovalsOut(items=items)


@router.post("/{thread_id}", response_model=ApprovalResult)
async def answer(thread_id: str, body: ApprovalIn, state: State, user: User) -> ApprovalResult:
    known = await state.thread(user["username"], thread_id)
    if known is None:
        raise HTTPException(404, "no such thread")
    if await state.pending(known["kind"], thread_id) is None:
        raise HTTPException(409, "nothing is waiting for approval on this thread")
    try:
        approval = Approval.model_validate(body.model_dump())
    except ValidationError as err:
        raise HTTPException(422, str(err.errors()[0]["msg"])) from err
    ctx = await state.context(user)
    result = await invoke(state.graph(known["kind"]), Command(resume=approval.model_dump()), thread_id, ctx)
    promoted = await state.learn(user["username"], result) if known["kind"] == "bid" else []
    return ApprovalResult(thread_id=thread_id, status=result.get("status"), submission=result.get("submission"),
                          pending=await state.pending(known["kind"], thread_id), promoted_memory=promoted,
                          errors=result.get("errors", []))
