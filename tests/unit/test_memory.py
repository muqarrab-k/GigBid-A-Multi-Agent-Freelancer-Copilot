from langgraph.store.memory import InMemoryStore

from agent.config import get_config
from agent.memory.promotion_rules import edit_patterns, should_promote
from agent.memory.store import (
    delete_memory,
    learn_from_edits,
    learn_from_events,
    list_memory,
    style_rules,
)

BEFORE = ("I am passionate about chatbots and would love to help. You need a support bot that answers from your docs. "
          "I would start with a small prototype.")
AFTER = "You need a support bot that answers from your docs. I would start with a small prototype."


def edit(i: int, before: str = BEFORE, after: str = AFTER) -> dict[str, str]:
    return {"thread_id": f"job{i}:reviewer", "job_id": f"job{i}", "diff": f"diff {i}", "before": before,
            "after": after, "at": f"2026-11-15T10:0{i}:00"}


def test_edit_patterns_name_the_change() -> None:
    found, against = edit_patterns(BEFORE, AFTER, get_config().memory.style)
    keys = {p.key for p in found}
    assert {"cut_first_sentence", "removed_term:passionate"} <= keys and not against


async def test_promotes_only_after_repeats() -> None:
    store = InMemoryStore()
    assert await learn_from_edits(store, "reviewer", [edit(1)]) == []
    assert await learn_from_edits(store, "reviewer", [edit(2)]) == []
    # the same edit twice is not a repeat
    assert await learn_from_edits(store, "reviewer", [edit(2)]) == []
    promoted = await learn_from_edits(store, "reviewer", [edit(3)])
    assert "cut_first_sentence" in promoted and "removed_term:passionate" in promoted
    items = {i["key"]: i for i in await list_memory(store, "reviewer")}
    why = items["removed_term:passionate"]
    assert len(why["source_edits"]) == 3 and "min_repeats=3" in why["why"]
    assert any("passionate" in r for r in await style_rules(store, "reviewer"))
    # other users see nothing
    assert await list_memory(store, "someone_else") == []


def test_contradicting_edit_blocks_promotion() -> None:
    cfg = get_config().memory.style
    history = [{"patterns": ["removed_term:passionate"], "against": []}] * 3
    assert should_promote("removed_term:passionate", history, cfg)
    assert not should_promote("removed_term:passionate", [*history, {"patterns": [], "against": ["removed_term:passionate"]}], cfg)


async def test_delete_forgets_and_needs_new_repeats() -> None:
    store = InMemoryStore()
    await learn_from_edits(store, "reviewer", [edit(1), edit(2), edit(3)])
    assert await delete_memory(store, "reviewer", "style", "removed_term:passionate")
    assert not any(i["key"] == "removed_term:passionate" for i in await list_memory(store, "reviewer"))
    assert not await delete_memory(store, "reviewer", "style", "removed_term:passionate")
    # the old edits no longer count
    assert "removed_term:passionate" not in await learn_from_edits(store, "reviewer", [edit(4)])


async def test_outcome_memory_needs_the_rule() -> None:
    store = InMemoryStore()

    def ev(i: int, status: str) -> dict[str, object]:
        return {"event_id": i, "type": "proposal.status_changed",
                "data": {"proposal_id": f"pr{i % 10}", "job_id": f"j{i % 10}", "status": status}}

    cats = {f"j{i}": "ai_ml" for i in range(10)}
    few = [ev(i, "submitted") for i in range(4)] + [ev(10, "replied")]
    assert await learn_from_events(store, "reviewer", few, cats) == []
    more = [ev(i, "submitted") for i in range(4, 6)] + [ev(11, "replied")]
    assert await learn_from_events(store, "reviewer", more, cats) == ["ai_ml"]
    item = next(i for i in await list_memory(store, "reviewer") if i["kind"] == "outcome")
    assert item["submitted"] == 6 and item["replied"] == 2 and item["source_events"]
