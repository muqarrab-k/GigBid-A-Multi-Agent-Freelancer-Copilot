from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI


@dataclass(frozen=True)
class JudgeResult:
    score: float
    reason: str


SYSTEM_PROMPT = (
    "You are a strict rubric-based grader for tutor-bot answers. "
    "Return valid JSON with keys: score and reason. "
    "Score must be a number from 0 to 1."
)


def _parse_result(text: str) -> JudgeResult:
    data = json.loads(text)
    score = float(data["score"])
    reason = str(data["reason"]).strip()
    return JudgeResult(score=score, reason=reason)


def judge_answer(
    prompt: str,
    answer: str,
    rubric: str,
    model: str | None = None,
) -> JudgeResult:
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model_name = model or os.getenv("JUDGE_MODEL", "gpt-4o-mini")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Rubric:\n{rubric}\n\nPrompt:\n{prompt}\n\nAnswer:\n{answer}",
        },
    ]

    resp = client.chat.completions.create(
        model=model_name,
        messages=messages,
        temperature=0,
    )
    content = resp.choices[0].message.content or "{}"
    return _parse_result(content)
