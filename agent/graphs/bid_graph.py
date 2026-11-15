"""Bid graph: analysis fan-out -> decide -> pricing -> writer -> verifier -> critic -> compliance -> approval -> submit."""

from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import Command, Send

from agent.graphs.checkpoint import memory_saver
from agent.nodes.analyst import analyst
from agent.nodes.approval import (
    after_gate,
    apply_edit,
    approval_gate,
    prepare_approval,
    reject,
    submit,
)
from agent.nodes.common import BidContext
from agent.nodes.compliance import after_compliance, compliance
from agent.nodes.critic import after_critic, critic
from agent.nodes.decide import decide, over_budget
from agent.nodes.fit_matcher import fit_matcher
from agent.nodes.pricing import pricing
from agent.nodes.risk_assessor import risk_assessor
from agent.nodes.verifier import editing, verifier
from agent.nodes.writer import writer
from agent.profile import load_profile
from agent.state import BidState

PARALLEL = ["analyst", "risk_assessor", "fit_matcher"]
STATUS = {"skip": "skipped", "watch": "watching", "bid": "analysing"}
Graph = CompiledStateGraph[Any, Any, Any, Any]


def intake(state: BidState) -> dict[str, Any]:
    job = state["job"]
    today = state.get("today") or str(job.get("posted_at") or "")[:10] or "2024-08-01"
    return {"status": "analysing", "today": today, "step_count": 1,
            "trace": [{"node": "intake", "kind": "event", "data": {"job_id": job["job_id"]}}]}


def fan_out(state: BidState) -> list[Send]:
    return [Send(node, state) for node in PARALLEL]


def join(state: BidState, runtime: Runtime[BidContext]) -> dict[str, Any]:
    """All three branches are in; stop here if a budget ran out."""
    problem = over_budget(state, runtime.context.settings)
    if problem:
        return {"status": "needs_attention", "errors": [problem], "step_count": 1}
    return {"step_count": 1}


def after_join(state: BidState) -> str:
    return "stop" if state.get("status") == "needs_attention" else "decide"


def decide_node(state: BidState, runtime: Runtime[BidContext]) -> dict[str, Any]:
    ctx = runtime.context
    decision = decide(state, ctx.settings, load_profile(ctx.persona))
    return {"decision": decision, "status": STATUS[decision.action], "step_count": 1,
            "trace": [{"node": "decide", "kind": "decision",
                       "data": {"action": decision.action, "reasons": decision.reasons}}]}


def after_decide(state: BidState, runtime: Runtime[BidContext]) -> str:
    if state["decision"].action != "bid":
        return "end"
    return "end" if over_budget(state, runtime.context.settings) else "pricing"


def after_writer(state: BidState) -> str:
    return "end" if state.get("status") == "needs_attention" else "verifier"


def after_verifier(state: BidState) -> str:
    # human edits skip the critic
    return "compliance" if editing(state) else "critic"


def after_prepare(state: BidState) -> str:
    return "end" if state.get("status") == "queued" else "approval_gate"


def build_bid_graph(checkpointer: BaseCheckpointSaver[Any] | None = None,
                    stop_before: list[str] | None = None) -> Graph:
    graph = StateGraph(BidState, context_schema=BidContext)
    nodes = {"intake": intake, "analyst": analyst, "risk_assessor": risk_assessor, "fit_matcher": fit_matcher,
             "join": join, "decide": decide_node, "pricing": pricing, "writer": writer, "verifier": verifier,
             "critic": critic, "compliance": compliance, "prepare_approval": prepare_approval,
             "approval_gate": approval_gate, "apply_edit": apply_edit, "reject": reject, "submit": submit}
    for name, fn in nodes.items():
        graph.add_node(name, fn)  # type: ignore[call-overload]
    graph.add_edge(START, "intake")
    graph.add_conditional_edges("intake", fan_out, PARALLEL)
    for node in PARALLEL:
        graph.add_edge(node, "join")
    graph.add_conditional_edges("join", after_join, {"decide": "decide", "stop": END})
    graph.add_conditional_edges("decide", after_decide, {"pricing": "pricing", "end": END})
    graph.add_edge("pricing", "writer")
    graph.add_conditional_edges("writer", after_writer, {"verifier": "verifier", "end": END})
    graph.add_conditional_edges("verifier", after_verifier, {"critic": "critic", "compliance": "compliance"})
    graph.add_conditional_edges("critic", after_critic, {"writer": "writer", "compliance": "compliance"})
    graph.add_conditional_edges("compliance", after_compliance, {"prepare_approval": "prepare_approval", "end": END})
    graph.add_conditional_edges("prepare_approval", after_prepare, {"approval_gate": "approval_gate", "end": END})
    graph.add_conditional_edges("approval_gate", after_gate,
                                {"submit": "submit", "apply_edit": "apply_edit", "reject": "reject"})
    graph.add_edge("apply_edit", "verifier")
    graph.add_edge("reject", END)
    graph.add_edge("submit", END)
    return graph.compile(checkpointer=checkpointer or memory_saver(), interrupt_before=stop_before)


def thread_config(thread_id: str, ctx: BidContext) -> RunnableConfig:
    return {"configurable": {"thread_id": thread_id}, "recursion_limit": ctx.settings.budgets.max_graph_steps}


async def invoke(graph: Graph, payload: Any, thread_id: str, ctx: BidContext) -> dict[str, Any]:
    """Run with retries; after N failures the thread is dead-lettered."""
    config = thread_config(thread_id, ctx)
    errors = []
    for attempt in range(ctx.settings.nodes.max_attempts):
        started = bool((await graph.aget_state(config)).values)
        try:
            # retries continue from the last checkpoint
            result: dict[str, Any] = await graph.ainvoke(None if attempt and started else payload,
                                                         config=config, context=ctx)
            return result
        except Exception as err:  # noqa: BLE001
            errors.append(f"attempt {attempt + 1}: {type(err).__name__}: {err}"[:300])
    update = {"status": "dead_letter", "errors": errors}
    await graph.aupdate_state(config, update)
    return {**(await graph.aget_state(config)).values}


async def run_job(job: dict[str, Any], ctx: BidContext, today: str | None = None,
                  graph: Graph | None = None, thread_id: str | None = None) -> dict[str, Any]:
    """One bid-graph thread per job; stops at the approval interrupt."""
    graph = graph or build_bid_graph()
    thread_id = thread_id or job["job_id"]
    state: dict[str, Any] = {"job": job, "thread_id": thread_id, "persona": ctx.persona,
                             **({"today": today} if today else {})}
    return await invoke(graph, state, thread_id, ctx)


async def resume_job(thread_id: str, answer: dict[str, Any], ctx: BidContext, graph: Graph) -> dict[str, Any]:
    """Answer the approval interrupt: approve, edit(edited_text) or reject(reason)."""
    return await invoke(graph, Command(resume=answer), thread_id, ctx)


def pending_approval(result: dict[str, Any]) -> dict[str, Any] | None:
    found = result.get("__interrupt__")
    return found[0].value if found else None
