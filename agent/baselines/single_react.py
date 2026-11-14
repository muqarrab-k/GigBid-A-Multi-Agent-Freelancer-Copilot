"""One ReAct agent with read tools and dry-run drafting: the RQ-C single-agent baseline."""

import json
import time
from typing import Any

from langchain_core.language_models import LanguageModelInput
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.runnables import Runnable
from langgraph.prebuilt import create_react_agent

from agent.llm import get_model
from agent.mcp_client import McpLayer, trace
from agent.prompts.loader import load_prompt

AGENT = "single_react"
RECURSION_LIMIT = 30


def task(job_id: str) -> str:
    return f"Draft a grounded proposal for job id {job_id}. Follow your steps and finish with the dry run."


def tool_log(messages: list[BaseMessage]) -> list[dict[str, Any]]:
    """Tool calls paired with their results."""
    results = {m.tool_call_id: m.content for m in messages if isinstance(m, ToolMessage)}
    calls = []
    for msg in messages:
        if isinstance(msg, AIMessage):
            for call in msg.tool_calls:
                raw = results.get(call["id"] or "", "")
                try:
                    result: Any = json.loads(raw) if isinstance(raw, str) else raw
                except ValueError:
                    result = raw
                calls.append({"tool": call["name"], "args": call["args"], "result": result})
    return calls


def tokens(messages: list[BaseMessage]) -> dict[str, int]:
    total = {"input_tokens": 0, "output_tokens": 0}
    for msg in messages:
        usage = getattr(msg, "usage_metadata", None) or {}
        for key in total:
            total[key] += int(usage.get(key, 0))
    return total


async def run_single(job_id: str, layer: McpLayer,
                     model: Runnable[LanguageModelInput, BaseMessage] | None = None) -> dict[str, Any]:
    """Run the agent on one job and return the full record."""
    tools = layer.get_tools(AGENT)
    agent = create_react_agent(model or get_model("writer"), tools,  # type: ignore[arg-type]
                               prompt=load_prompt("single_react"))
    start = time.perf_counter()
    with trace() as trace_id:
        state = await agent.ainvoke({"messages": [HumanMessage(content=task(job_id))]},
                                    config={"recursion_limit": RECURSION_LIMIT})
    messages: list[BaseMessage] = state["messages"]
    calls = tool_log(messages)
    drafts = [c for c in calls if c["tool"] == "create_proposal_draft"]
    final = next((m.content for m in reversed(messages) if isinstance(m, AIMessage) and not m.tool_calls), "")
    return {
        "job_id": job_id,
        "trace_id": trace_id,
        "tools_offered": [t.name for t in tools],
        "tool_calls": calls,
        "final_answer": final,
        "dry_run_preview": drafts[-1]["result"] if drafts else None,
        "tokens": tokens(messages),
        "latency_s": round(time.perf_counter() - start, 2),
        "steps": len(messages),
    }
