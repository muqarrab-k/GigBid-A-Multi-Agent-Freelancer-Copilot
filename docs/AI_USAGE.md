# AI Usage Disclosure

Record the AI coding assistant/tool used, the files or tasks it helped with, and at least
one incorrect suggestion you identified and corrected. You remain responsible for all code.

## Log

| date | tool | files / task | what it got wrong (caught) |
|---|---|---|---|
| 2026-11-14 | Claude Code (Claude Opus 5.5) | Foundation: `agent/config.*`, `handoffs.py`, `state.py`, `llm.py`, prompt loader, unit tests | Latest `mcp` (2.3.0) conflicts with `langchain-mcp-adapters` (needs `mcp<2`); found by checking package metadata, pinned 1.30.0. |
| 2026-11-14 | Claude Code (Claude Opus 5.5) | Real-data pipeline: `data_pipeline/`, `docs/DATA_CARD.md`, `docs/data_profile.md`, `gigsim/seed/` | Its first duplicate rule grouped title-only jobs by title alone, which merged 98 unrelated "Social Media Manager" posts; unpriced title-only rows are now never grouped. Its first scam-signal list was dominated by one company's reposted ads. `kaggle` 2.2.5 imports `six` without declaring it, so `six` is pinned. |
| 2026-11-14 | Claude Code (Claude Opus 5.5) | Synthetic data: persona `facts.yaml`, `synth/`, `evals/datasets/labeling_rules.py`, `policy_rules.yaml`, clients, plants, dev labels | Its first fair-price band used only market percentiles, so a job posting $80-175/h got a band of $15-39; bands now follow the posted budget. Its first client assignment gave one client 179 jobs (now capped at 30). Its YAML metrics lists split "2,300 hours" into two items. Its first rate floors were above the expert medians and left only 10% of dev jobs as bids. |
