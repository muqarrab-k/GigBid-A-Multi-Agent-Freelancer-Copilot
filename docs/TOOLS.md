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
| GitHub MCP (`ghcr.io/github/github-mcp-server:v2.0.3`, stdio via Docker) | GitHub | reading README and code for portfolio ingestion (`rag/ingest/github_loader.py`, only `get_file_contents`) | Official server from GitHub, pinned image tag, `GITHUB_READ_ONLY=1` with only the `repos` toolset, and a fine-grained token scoped to read-only contents of the chosen repos. |
| Upwork MCP (`https://mcp.upwork.com/mcp`) | Upwork | live mode (next task) | |

## Agent tool allowlists (`mcp_client.allowlists` in `agent/config.yaml`)

`agent/mcp_client.py` discovers tools on every server once and gives each agent only the tool
names on its list; an unknown name fails at startup. Every call carries a `trace_id` in the MCP
request meta (it lands in the server audit logs), has a timeout and bounded retries, and wraps
`untrusted_text` in `<untrusted>` tags before a model sees it. If the marketplace is unreachable,
calls return a typed `MarketplaceDown` result. `search_evidence` defaults to portfolio types
(case study, README, code, review, CV); past proposals need an explicit `types` filter.

| agent | tools |
|---|---|
| scout, risk_assessor, pricing | marketplace read: search_jobs, get_job, get_client_history, get_connects_balance, list_proposals, list_threads, list_messages, get_events, get_policy |
| analyst, compliance | none |
| fit_matcher, writer, verifier, critic | portfolio read: search_evidence, get_case_study, list_skills |
| client_liaison | marketplace read + create_proposal_draft, submit_proposal, send_message (writes only after approval, enforced by the graph) + workspace: free_slots, create_tentative_hold, create_email_draft |
| single_react (RQ-C baseline) | marketplace read (search_jobs, get_job, get_client_history, get_connects_balance, get_policy), create_proposal_draft forced to dry_run, portfolio read; never submit_proposal or send_message |
