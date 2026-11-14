# LLM evaluation harness

Regression harness for grading tutor-bot answers against a 400-item rubric before release.

## Setup

Install dependencies in a Python environment with `pytest`, the OpenAI API client setup you use for model calls, and access to vLLM for local model serving.

## Usage

Run the regression test suite with:

```bash
pytest test_regressions.py
```

`judge.py` contains the rubric-based grader. It sends a prompt to a model, gets back a score and short reason, and returns the result for each item. `test_regressions.py` aggregates rubric scores and fails when the average score drops below the expected threshold.

## Notes

Built for release gating in an edtech tutor-bot workflow.

The grading pass was checked against human review during development and showed solid agreement. It also caught regressions before release.

This repository is intentionally small: one grader, one pytest gate, and a rubric-driven check that can be wired into CI.
