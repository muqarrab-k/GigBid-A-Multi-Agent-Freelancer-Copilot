"""Bid graph, analysis half: intake -> (analyst | risk | fit) in parallel -> decide -> pricing."""

from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from langgraph.types import Send

from agent.nodes.analyst import analyst
from agent.nodes.common import BidContext
from agent.nodes.decide import decide, over_budget
from agent.nodes.fit_matcher import fit_matcher
from agent.nodes.pricing import pricing
from agent.nodes.risk_assessor import risk_assessor
from agent.profile import load_profile
from agent.state import BidState

PARALLEL = ["analyst", "risk_assessor", "fit_matcher"]
STATUS = {"skip": "skipped", "watch": "watching", "bid": "analysing"}


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


def build_bid_graph(checkpointer: BaseCheckpointSaver[Any] | None = None) -> CompiledStateGraph[Any, Any, Any, Any]:
    graph = StateGraph(BidState, context_schema=BidContext)
    graph.add_node("intake", intake)
    graph.add_node("analyst", analyst)
    graph.add_node("risk_assessor", risk_assessor)
    graph.add_node("fit_matcher", fit_matcher)
    graph.add_node("join", join)
    graph.add_node("decide", decide_node)
    graph.add_node("pricing", pricing)
    graph.add_edge(START, "intake")
    graph.add_conditional_edges("intake", fan_out, PARALLEL)
    for node in PARALLEL:
        graph.add_edge(node, "join")
    graph.add_conditional_edges("join", after_join, {"decide": "decide", "stop": END})
    graph.add_conditional_edges("decide", after_decide, {"pricing": "pricing", "end": END})
    graph.add_edge("pricing", END)
    return graph.compile(checkpointer=checkpointer or MemorySaver())


async def run_job(job: dict[str, Any], ctx: BidContext, today: str | None = None,
                  graph: CompiledStateGraph[Any, Any, Any, Any] | None = None) -> dict[str, Any]:
    """One bid-graph thread per job."""
    graph = graph or build_bid_graph()
    state: dict[str, Any] = {"job": job, "thread_id": job["job_id"], **({"today": today} if today else {})}
    result: dict[str, Any] = await graph.ainvoke(state, config={"configurable": {"thread_id": job["job_id"]}},
                                                 context=ctx)
    return result
