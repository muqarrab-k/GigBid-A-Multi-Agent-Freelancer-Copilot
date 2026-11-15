"""Conversation graph: one thread per client conversation, nothing is sent without a human."""

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from agent.graphs.bid_graph import Graph, invoke
from agent.graphs.checkpoint import memory_saver
from agent.nodes.client_liaison import (
    LiaisonState,
    after_classify,
    after_gate,
    after_guard,
    after_read,
    apply_edit,
    approval_gate,
    classify,
    guard,
    prepare_reply,
    propose_slots,
    read_messages,
    reject,
    send,
)
from agent.nodes.common import BidContext


def build_conversation_graph(checkpointer: BaseCheckpointSaver[Any] | None = None) -> Graph:
    graph = StateGraph(LiaisonState, context_schema=BidContext)
    nodes = {"read_messages": read_messages, "classify": classify, "propose_slots": propose_slots, "guard": guard,
             "prepare_reply": prepare_reply, "approval_gate": approval_gate, "apply_edit": apply_edit,
             "reject": reject, "send": send}
    for name, fn in nodes.items():
        graph.add_node(name, fn)  # type: ignore[call-overload]
    graph.add_edge(START, "read_messages")
    graph.add_conditional_edges("read_messages", after_read, {"classify": "classify", "end": END})
    graph.add_conditional_edges("classify", after_classify,
                                {"propose_slots": "propose_slots", "guard": "guard", "end": END})
    graph.add_edge("propose_slots", "guard")
    graph.add_conditional_edges("guard", after_guard, {"prepare_reply": "prepare_reply", "end": END})
    graph.add_edge("prepare_reply", "approval_gate")
    graph.add_conditional_edges("approval_gate", after_gate,
                                {"send": "send", "apply_edit": "apply_edit", "reject": "reject"})
    # edited text goes through the guard again
    graph.add_edge("apply_edit", "guard")
    graph.add_edge("send", END)
    graph.add_edge("reject", END)
    return graph.compile(checkpointer=checkpointer or memory_saver())


def conversation_id(user: str, thread_id: str) -> str:
    return f"conv:{user}:{thread_id}"


async def run_conversation(thread_id: str, ctx: BidContext, graph: Graph, user: str,
                           job_title: str | None = None) -> dict[str, Any]:
    """Read the thread's new messages and stop at the approval interrupt."""
    cid = conversation_id(user, thread_id)
    state: dict[str, Any] = {"thread_id": thread_id, "conversation_id": cid, "persona": ctx.persona,
                             **({"job_title": job_title} if job_title else {})}
    return await invoke(graph, state, cid, ctx)


async def resume_conversation(cid: str, answer: dict[str, Any], ctx: BidContext, graph: Graph) -> dict[str, Any]:
    return await invoke(graph, Command(resume=answer), cid, ctx)
