# MCP Tool Inventory

Agents reach every external capability through MCP tools. The flow for the marketplace is
`agent -> Marketplace MCP server -> MarketplacePort (agent/marketplace_port.py) -> adapter`
(GigSim now, live Upwork later). No agent calls GigSim or Upwork directly.

Every tool has a Pydantic input schema (bounds from `mcp.limits` in `agent/config.yaml`), a
declared output schema, and annotations. Results always carry `ok`; failures come back with
`isError: true` and `{"ok": false, "error": {"code", "detail", "retry_after", "rule_id"}}`.
Exact schemas are snapshotted in `tests/contract/snapshots/` (CI fails on unintended changes;
`make snapshot-update` regenerates them on purpose).

**Auth.** Streamable HTTP needs `Authorization: Bearer <token>`; each token maps to one user and
tenant in `mcp.users` (`MCP_TOKEN_*` env vars, dev defaults for local runs only). stdio runs as
`mcp.default_user`. **Writes** need an `idempotency_key` (8 to 200 characters) and accept
`dry_run`. **Rate limit:** per user, 20 requests/minute with a burst of 10 (below GigSim's 30/0.5 s).
**Audit:** every call is appended to `data/audit/<server>.jsonl` with user, tenant, tool, masked
args, result summary, `dry_run` and `trace_id`.

## Marketplace server (`mcp_servers/marketplace/server.py`)

Annotations: R = readOnlyHint, D = destructiveHint, I = idempotentHint, O = openWorldHint.

| tool | read/write | R | D | I | O | auth | notes |
|---|---|---|---|---|---|---|---|
| `search_jobs` | read | yes | no | yes | yes | bearer (HTTP) | filters: q, skills, budget type, fixed and hourly ranges, posted_after, limit, offset; job text in `untrusted_text` |
| `get_job` | read | yes | no | yes | yes | bearer (HTTP) | includes `connects_cost` under the current policy |
| `get_client_history` | read | yes | no | yes | yes | bearer (HTTP) | public history only |
| `get_connects_balance` | read | yes | no | yes | yes | bearer (HTTP) | balance, weekly amount, next refill |
| `list_proposals` | read | yes | no | yes | yes | bearer (HTTP) | optional status filter |
| `list_threads` | read | yes | no | yes | yes | bearer (HTTP) | threads opened by clients |
| `list_messages` | read | yes | no | yes | yes | bearer (HTTP) | client text in `untrusted_text` |
| `get_events` | read | yes | no | yes | yes | bearer (HTTP) | cursor feed of status changes and messages |
| `get_policy` | read | yes | no | yes | yes | bearer (HTTP) | platform rules plus adapter `capabilities` |
| `create_proposal_draft` | write | no | no | yes | yes | bearer (HTTP) | idempotency_key, dry_run; returns cost and policy pre-check |
| `submit_proposal` | write | no | **yes** | yes | yes | bearer (HTTP) | spends Connects; dry_run shows payload, cost, balance after, blockers; human approval required upstream |
| `send_message` | write | no | **yes** | yes | yes | bearer (HTTP) | banned-content pre-check; human approval required upstream |

## Workspace server (`mcp_servers/workspace/server.py`, documented local mock)

A seeded local calendar per persona (working hours 9 to 17 in the persona's timezone, two
seeded meetings a day) plus a runtime file of holds and drafts in `data/workspace/`
(git-ignored). Nothing is ever sent. Google Calendar (free/busy, events.insert with
`status: tentative`) and Gmail (drafts.create) could replace the mock behind the same tool
names and schemas.

| tool | read/write | R | D | I | O | auth | notes |
|---|---|---|---|---|---|---|---|
| `free_slots` | read | yes | no | yes | no | bearer (HTTP) | start, end (max 14 days), duration 15 to 240 min, results in the given IANA timezone |
| `create_tentative_hold` | write | no | no | yes | no | bearer (HTTP) | idempotency_key, dry_run; rejects taken or out-of-hours slots |
| `create_email_draft` | write | no | no | yes | no | bearer (HTTP) | idempotency_key, dry_run; draft only, never sent |

## Portfolio server (`mcp_servers/portfolio/server.py`, read-only)

Search over one freelancer's own portfolio, scoped by token: each user sees only their tenant's
evidence (`mcp.users[].tenant`). Retrieval uses the configured RAG variant (`rag.variant`, V0 now)
over pgvector. With `PORTFOLIO_DIR` set it indexes any folder of md, pdf and code into memory instead.

| tool | read/write | R | D | I | O | auth | notes |
|---|---|---|---|---|---|---|---|
| `search_evidence` | read | yes | no | yes | no | bearer (HTTP) | requirement, k (1 to 20), filters: types, project, outcomes; returns evidence_id, type, source, date, outcome, score, snippet |
| `get_case_study` | read | yes | no | yes | no | bearer (HTTP) | project id (`p05`) or evidence id; full text |
| `list_skills` | read | yes | no | yes | no | bearer (HTTP) | skills with evidence counts and projects; `implied` when only the fact sheet's implied tags show it |

Resources: `portfolio://case/{case_id}`, `portfolio://proposal/{proposal_id}`,
`portfolio://repo/{name}`, `portfolio://cv`. Prompts: `answer_screening_question`, `find_proof`,
`pick_best_projects` (text in `agent/prompts/portfolio_*.v1.md`).

## Third-party servers + trust rationale

| server | owner | used for | trust rationale |
|---|---|---|---|
| Upwork MCP (`https://mcp.upwork.com/mcp`) | Upwork | live mode (later task) | |
| GitHub MCP | GitHub | repo ingestion (later task) | |
