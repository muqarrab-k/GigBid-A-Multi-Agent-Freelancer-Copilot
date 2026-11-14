# AI Usage Disclosure

Record the AI coding assistant/tool used, the files or tasks it helped with, and at least
one incorrect suggestion you identified and corrected. You remain responsible for all code.

## Log

| date | tool | files / task | what it got wrong (caught) |
|---|---|---|---|
| 2026-11-14 | Claude Code (Claude Opus 5.5) | Foundation: `agent/config.*`, `handoffs.py`, `state.py`, `llm.py`, prompt loader, unit tests | Latest `mcp` (2.3.0) conflicts with `langchain-mcp-adapters` (needs `mcp<2`); found by checking package metadata, pinned 1.30.0. |
| 2026-11-14 | Claude Code (Claude Opus 5.5) | Real-data pipeline: `data_pipeline/`, `docs/DATA_CARD.md`, `docs/data_profile.md`, `gigsim/seed/` | Its first duplicate rule grouped title-only jobs by title alone, which merged 98 unrelated "Social Media Manager" posts; unpriced title-only rows are now never grouped. Its first scam-signal list was dominated by one company's reposted ads. `kaggle` 2.2.5 imports `six` without declaring it, so `six` is pinned. |
