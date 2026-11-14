import json
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from agent.baselines.single_react import run_single
from mcp_servers.conftest import LETTER
from tests.unit.agent_fixtures import gigsim, layer_for, servers


class ScriptedModel(BaseChatModel):
    """Replays fixed AI messages, one per model call."""

    script: list[AIMessage]
    seen: dict[str, Any] = Field(default_factory=dict)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedModel":
        self.seen["tools"] = [t.name for t in tools]
        return self

    def _generate(self, messages: list[BaseMessage], stop: Any = None, run_manager: Any = None,
                  **kwargs: Any) -> ChatResult:
        step = self.seen.get("step", 0)
        self.seen["step"] = step + 1
        return ChatResult(generations=[ChatGeneration(message=self.script[min(step, len(self.script) - 1)])])


def call(name: str, args: dict[str, Any], n: int) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"c{n}"}])


async def test_single_agent_never_submits_or_sends(tmp_path: Path) -> None:
    app = gigsim(tmp_path)
    found = servers(tmp_path, app)
    layer = layer_for(found)
    await layer.discover()
    job = (await layer.call("search_jobs", {"q": "python", "limit": 1}))["items"][0]["job_id"]
    model = ScriptedModel(script=[
        call("get_job", {"job_id": job}, 1),
        call("search_evidence", {"requirement": "python machine learning", "k": 3}, 2),
        call("create_proposal_draft", {"job_id": job, "cover_letter": LETTER, "bid_amount": 100,
                                       "idempotency_key": "single-test-0001", "dry_run": False}, 3),
        call("submit_proposal", {"proposal_id": "pr_000001", "idempotency_key": "single-test-0002"}, 4),
        AIMessage(content="Proposal text [ai_ml:case_study:p01]\nEvidence: ai_ml:case_study:p01\nRed flags: none"),
    ])

    run = await run_single(job, layer, model)

    assert not set(model.seen["tools"]) & {"submit_proposal", "send_message"}
    assert run["dry_run_preview"]["dry_run"] is True and run["dry_run_preview"]["proposal"] is None
    assert app.state.ctx.store.one("SELECT COUNT(*) AS n FROM proposals")["n"] == 0
    audit = [json.loads(x)["tool"] for x in (tmp_path / "marketplace.jsonl").read_text().splitlines()]
    assert "submit_proposal" not in audit and "send_message" not in audit
    submit = next(c for c in run["tool_calls"] if c["tool"] == "submit_proposal")
    assert "not a valid tool" in str(submit["result"])
    assert run["final_answer"].startswith("Proposal text") and run["trace_id"]
