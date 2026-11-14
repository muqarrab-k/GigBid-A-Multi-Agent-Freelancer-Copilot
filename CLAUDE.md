# GigBid

Multi-agent freelancer copilot (LangGraph + MCP + advanced RAG + FastAPI + React) for AI-4016 Assignment II.
Author: Muqarrab · i230511 · Section C

## Code style
- Write like a careful student by hand: natural names, small functions, no over-engineering,
  no unused helpers, no placeholder "framework" code.
- Comments are rare and 2-3 words max: `#` in Python (`# load config`), `//` in TS (`// fetch jobs`).
- Docstrings at most one short line. No banner comments, no emojis, no "This function does X".
- Type hints everywhere. Pydantic v2.

## Hard rules
- No secrets in code or git. Every variable goes in `.env.example` with an empty value.
- Prompts live only in `agent/prompts/<node>.vN.md`, never inline.
- Models, budgets, thresholds and platform rules live in `agent/config.yaml`, never in code.
  A policy change must be a config edit.
- Never invent metrics. Every reported number comes from a file in `evals/results/` or the data pipeline.
- Raw data (`data/raw/`) and generated data (`data/processed/`) are git-ignored.
- Real and synthetic data stay clearly separated and labelled. Never fabricate a value inside real data.
- `gigsim/` is ours to build: the instructor did not provide it, and their note says to build it
  from the Kaggle datasets.
- Do not touch `data/policy_pack/`.
- No Claude co-author trailer in commits. Keep commit messages short and natural.

## Commands
- `make install` (uv if present, else pip) and `make data` (download, inspect, build, seed split)
- `make test`, `make lint`, `make dev`
- `make eval`, `make seed`, `make demo` are stubs for now
