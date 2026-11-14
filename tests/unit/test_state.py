from typing import Any

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import InvalidUpdateError
from langgraph.graph import END, START, StateGraph

from agent.handoffs import Critique, EvidenceItem, FitReport, JobSpec, RiskReport
from agent.state import BidState, ConversationState, ThreadMessage, merge_evidence, merge_messages


def item(eid: str, text: str = "x") -> EvidenceItem:
    return EvidenceItem(evidence_id=eid, type="case_study", source="cv", text=text)


def msg(mid: str) -> ThreadMessage:
    return {"message_id": mid, "sender": "client", "text": "hi", "sent_at": "2026-11-14"}


def test_merge_evidence_dedupes_newer_wins() -> None:
    merged = merge_evidence([item("e1", "old"), item("e2")], [item("e1", "new"), item("e3")])
    assert [e.evidence_id for e in merged] == ["e1", "e2", "e3"]
    assert merged[0].text == "new"


def test_merge_messages_skips_seen() -> None:
    merged = merge_messages([msg("m1")], [msg("m1"), msg("m2")])
    assert [m["message_id"] for m in merged] == ["m1", "m2"]


def analyst(state: BidState) -> dict[str, Any]:
    return {
        "job_spec": JobSpec(job_id="j1", title="t"),
        "token_count": 100,
        "step_count": 1,
        "trace": [{"node": "analyst", "kind": "done", "data": {}}],
    }


def risk(state: BidState) -> dict[str, Any]:
    return {
        "risk_report": RiskReport(score=0.1, explanation="fine"),
        "evidence": [item("e1")],
        "token_count": 50,
        "step_count": 1,
        "errors": ["client history slow"],
        "trace": [{"node": "risk", "kind": "done", "data": {}}],
    }


def fit(state: BidState) -> dict[str, Any]:
    return {
        "fit_report": FitReport(score=0.7),
        "evidence": [item("e1"), item("e2")],
        "token_count": 25,
        "step_count": 1,
        "trace": [{"node": "fit", "kind": "done", "data": {}}],
    }


def build_parallel() -> StateGraph[BidState, None, BidState, BidState]:
    graph = StateGraph(BidState)
    for name, fn in (("analyst", analyst), ("risk", risk), ("fit", fit)):
        graph.add_node(name, fn)
        graph.add_edge(START, name)
        graph.add_edge(name, END)
    return graph


def test_parallel_branches_merge_without_clash() -> None:
    app = build_parallel().compile(checkpointer=InMemorySaver())
    out = app.invoke({"job": {"id": "j1"}}, {"configurable": {"thread_id": "t1"}})

    assert out["token_count"] == 175
    assert out["step_count"] == 3
    assert out["errors"] == ["client history slow"]
    assert {e.evidence_id for e in out["evidence"]} == {"e1", "e2"}
    assert sorted(t["node"] for t in out["trace"]) == ["analyst", "fit", "risk"]
    assert isinstance(out["fit_report"], FitReport)


def test_plain_field_clashes_in_parallel() -> None:
    # why reducers matter
    graph = StateGraph(BidState)
    graph.add_node("a", lambda s: {"status": "analysing"})
    graph.add_node("b", lambda s: {"status": "drafting"})
    graph.add_edge(START, "a")
    graph.add_edge(START, "b")
    with pytest.raises(InvalidUpdateError):
        graph.compile().invoke({})


def test_critiques_append_across_loop() -> None:
    def critic(state: BidState) -> dict[str, Any]:
        count = len(state.get("critiques", []))
        verdict = "revise" if count < 2 else "pass"
        reasons = ["too generic"] if verdict == "revise" else []
        return {"critiques": [Critique(verdict=verdict, reasons=reasons, revision_count=count)]}

    def route(state: BidState) -> str:
        return "critic" if state["critiques"][-1].verdict == "revise" else END

    graph = StateGraph(BidState)
    graph.add_node("critic", critic)
    graph.add_edge(START, "critic")
    graph.add_conditional_edges("critic", route)
    out = graph.compile().invoke({})
    assert [c.verdict for c in out["critiques"]] == ["revise", "revise", "pass"]


def test_conversation_messages_merge_in_graph() -> None:
    graph = StateGraph(ConversationState)
    graph.add_node("poll", lambda s: {"messages": [msg("m1"), msg("m2")], "step_count": 1})
    graph.add_edge(START, "poll")
    graph.add_edge("poll", END)
    out = graph.compile().invoke({"messages": [msg("m1")]})
    assert [m["message_id"] for m in out["messages"]] == ["m1", "m2"]
