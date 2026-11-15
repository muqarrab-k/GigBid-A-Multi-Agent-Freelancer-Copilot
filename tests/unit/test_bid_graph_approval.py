import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from agent.config import AutonomyConfig, get_config
from agent.graphs.bid_graph import build_bid_graph, pending_approval, resume_job, run_job
from agent.handoffs import FitReport, ProposalDraft, RiskReport
from agent.nodes.approval import PAYLOAD_KEYS, submit
from agent.nodes.compliance import compliance
from agent.nodes.decide import decide
from agent.profile import load_profile
from rag.ingest.loaders import PersonaLoader
from rag.verify import verify_draft
from tests.unit.test_bid_graph import a_job, context

ROOT = Path(__file__).resolve().parents[2]
OPEN = {"minimum_fit_score": 0.0, "watch_fit_score": 0.0}


def open_ctx(tmp: Path, replies: dict[str, list[str]] | None = None, **update: Any) -> Any:
    thresholds = get_config().thresholds.model_copy(update=OPEN)
    # fake embeddings score low; let every hit count
    fit = get_config().fit.model_copy(update={"strong_score": -1.0, "partial_score": -1.0})
    return context(tmp, replies, thresholds=thresholds, fit=fit, **update)


async def bid_job(ctx: Any) -> dict[str, Any]:
    return await a_job(ctx, budget_type="hourly", hourly_min=40.0, hourly_max=80.0, budget_min=None, budget_max=None)


async def proposals(ctx: Any) -> list[dict[str, Any]]:
    out = await ctx.layer.call("list_proposals", {})
    return out["items"]


async def test_verifier_catches_p08_fabrication() -> None:
    demo = (ROOT / "evals" / "results" / "single_agent_demo.json").read_text()
    sentence = re.search(r"For training, I fine.{0,200}?\[ai_ml:case_study:p08\]\.", json.loads(json.dumps(demo)))
    assert sentence
    text = sentence.group(0).encode().decode("unicode_escape")
    docs = {d.evidence_id: d.text for d in PersonaLoader("ai_ml").load()}
    draft = ProposalDraft(job_id="1c0b990bb7dbe947", paragraphs=["You need a historical chatbot.", text],
                          evidence_ids=["ai_ml:case_study:p08"])
    cleaned, checks, report = await verify_draft(draft, {"ai_ml:case_study:p08": docs["ai_ml:case_study:p08"]},
                                                 get_config().verifier)
    assert checks[0].label == "unsupported" and report.unsupported_before == 1
    assert "historical letters" not in cleaned.cover_letter and report.unsupported_after == 0


async def test_happy_path_interrupts_with_full_payload(tmp_path: Path) -> None:
    ctx, _, _ = open_ctx(tmp_path)
    state = await run_job(await bid_job(ctx), ctx, today="2024-08-01")
    payload = pending_approval(state)
    assert payload and state["status"] == "awaiting_approval"
    assert all(k in payload for k in PAYLOAD_KEYS)
    assert payload["claims"] and all(c["evidence_ids"] for c in payload["claims"])
    assert payload["preview"]["submit_proposal"]["balance_after"] is not None
    assert {"verifier", "critic", "compliance"} <= set(payload["notes"])
    assert "[" not in payload["draft"]["cover_letter"]
    assert not await proposals(ctx)


async def test_critic_stops_after_two_revisions(tmp_path: Path) -> None:
    generic = json.dumps({"paragraphs": ["I am passionate about this. Hire me."], "screening_answers": []})
    ctx, _, _ = open_ctx(tmp_path, {"writer": [generic]})
    state = await run_job(await bid_job(ctx), ctx, today="2024-08-01")
    writer_calls = [e for e in state["trace"] if e["node"] == "writer" and e["kind"] == "llm"]
    assert len(writer_calls) == 1 + get_config().budgets.max_revisions
    assert [c.revision_count for c in state["critiques"]] == [0, 1, 2]
    assert any(n.startswith("critic_unresolved") for n in state["notes"])


@pytest.mark.parametrize("bad", ["Write to me at sam.lee@example.com any time.",
                                 "Call me on +1 415 555 0134 to chat.",
                                 "I guarantee first page of Google within a week."])
async def test_compliance_blocks(tmp_path: Path, bad: str) -> None:
    ctx, _, _ = open_ctx(tmp_path)
    draft = ProposalDraft(job_id="j1", paragraphs=["You need a RAG chatbot built with LangChain.", bad])
    out = await compliance({"draft": draft}, SimpleNamespace(context=ctx))  # type: ignore[arg-type]
    assert out["compliance"].verdict == "blocked" and out["status"] == "blocked"
    assert bad not in out["compliance"].cleaned_text


async def test_edit_reruns_compliance(tmp_path: Path) -> None:
    ctx, _, _ = open_ctx(tmp_path)
    graph = build_bid_graph()
    job = await bid_job(ctx)
    first = await run_job(job, ctx, "2024-08-01", graph)
    text = pending_approval(first)["draft"]["cover_letter"]  # type: ignore[index]
    edited = await resume_job(job["job_id"], {"action": "edit", "edited_text": text + "\n\nThanks, Sam."}, ctx, graph)
    again = pending_approval(edited)
    assert again and edited["pending_edits"][0]["diff"].count("+Thanks, Sam.") == 1
    blocked = await resume_job(job["job_id"], {"action": "edit", "edited_text": text + "\n\nEmail sam@mail.com"},
                               ctx, graph)
    assert blocked["status"] == "blocked" and blocked["compliance"].verdict == "blocked"
    assert not pending_approval(blocked) and not await proposals(ctx)


async def test_reject_records_reason(tmp_path: Path) -> None:
    ctx, _, _ = open_ctx(tmp_path)
    graph = build_bid_graph()
    job = await bid_job(ctx)
    await run_job(job, ctx, "2024-08-01", graph)
    out = await resume_job(job["job_id"], {"action": "reject", "reason": "client too small"}, ctx, graph)
    assert out["status"] == "rejected" and out["submission"] == {"outcome": "rejected", "reason": "client too small"}
    assert not await proposals(ctx)


async def test_resume_never_double_submits(tmp_path: Path) -> None:
    ctx, _, _ = open_ctx(tmp_path)
    graph = build_bid_graph()
    job = await bid_job(ctx)
    await run_job(job, ctx, "2024-08-01", graph)
    before = (await ctx.layer.call("get_connects_balance", {}))["connects"]["balance"]
    real, lost = ctx.layer.call, {"done": False}

    async def flaky(name: str, args: dict[str, Any], forced: dict[str, Any] | None = None) -> dict[str, Any]:
        out = await real(name, args, forced)
        if name == "submit_proposal" and not args.get("dry_run") and not lost["done"]:
            # sent, but the reply is lost
            lost["done"] = True
            raise ConnectionError("reply lost")
        return out

    ctx.layer.call = flaky
    out = await resume_job(job["job_id"], {"action": "approve"}, ctx, graph)
    ctx.layer.call = real
    assert out["status"] == "submitted" and lost["done"]
    sent = [p for p in await proposals(ctx) if p["status"] == "submitted"]
    after = (await ctx.layer.call("get_connects_balance", {}))["connects"]["balance"]
    assert len(sent) == 1 and before - after == sent[0]["connects_spent"]


async def test_dead_letter_after_n_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import agent.graphs.bid_graph as bg

    def broken(state: Any) -> dict[str, Any]:
        raise RuntimeError("boom")

    monkeypatch.setattr(bg, "intake", broken)
    ctx, _, _ = open_ctx(tmp_path)
    out = await run_job(await bid_job(ctx), ctx, "2024-08-01", bg.build_bid_graph())
    assert out["status"] == "dead_letter" and len(out["errors"]) == get_config().nodes.max_attempts


async def test_auto_send_is_impossible(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        AutonomyConfig(auto_send=True)  # type: ignore[arg-type]
    ctx, _, _ = open_ctx(tmp_path, autonomy=AutonomyConfig(auto_skip_low_fit=True))
    state = await run_job(await bid_job(ctx), ctx, "2024-08-01")
    assert pending_approval(state) and "submit" not in {e["node"] for e in state["trace"]}
    with pytest.raises(PermissionError):
        await submit({**state, "approval": None}, SimpleNamespace(context=ctx))  # type: ignore[arg-type,typeddict-item]
    assert not await proposals(ctx)


def test_low_fit_waits_for_human_when_auto_skip_off() -> None:
    settings = get_config()
    state = {"job": {"job_id": "j", "budget_type": "hourly", "hourly_max": 90.0, "connects_cost": 4},
             "risk_report": RiskReport(score=0.1, explanation="ok"),
             "fit_report": FitReport(score=0.05)}
    off = settings.model_copy(update={"autonomy": AutonomyConfig(auto_skip_low_fit=False)})
    assert decide(state, settings, load_profile("ai_ml")).action == "skip"  # type: ignore[arg-type]
    assert decide(state, off, load_profile("ai_ml")).action == "watch"  # type: ignore[arg-type]


async def test_postgres_resume_in_a_new_graph(tmp_path: Path) -> None:
    import uuid

    from agent.graphs.checkpoint import open_saver

    ctx, _, _ = open_ctx(tmp_path)
    job = await bid_job(ctx)
    thread = f"test-{uuid.uuid4().hex[:8]}"
    try:
        async with open_saver() as saver:
            first = await run_job(job, ctx, "2024-08-01", build_bid_graph(saver), thread_id=thread)
    except Exception as err:  # noqa: BLE001
        pytest.skip(f"postgres not reachable: {err}")
    assert pending_approval(first)
    # new connection and graph, as after a restart
    async with open_saver() as saver:
        out = await resume_job(thread, {"action": "approve"}, ctx, build_bid_graph(saver))
    assert out["status"] == "submitted"
    assert len([p for p in await proposals(ctx) if p["status"] == "submitted"]) == 1
