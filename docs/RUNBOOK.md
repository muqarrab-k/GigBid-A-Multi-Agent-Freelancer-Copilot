# Runbook

TODO: API, worker, deployment, degraded mode (later parts).

## GigSim (marketplace simulator)

Full API contract: [gigsim/README.md](../gigsim/README.md).

### Run

```bash
make gigsim
```

Serves on `http://localhost:8081`. On first start it creates `gigsim/data/gigsim.db` (git-ignored)
from `gigsim/seed/` in the scenario set in `gigsim/config.yaml` (`live` by default). Later starts
keep the existing database, including the simulated clock.

Docker:

```bash
docker compose -f infra/docker-compose.yml up gigsim
```

### Reset

Offline, server stopped or running:

```bash
make gigsim-reset
```

```bash
python -m gigsim.reset --scenario dev --seed 7
```

Through the API (server running):

```bash
curl -X POST localhost:8081/admin/reset -H "Authorization: Bearer $GIGSIM_ADMIN_TOKEN" -H "Content-Type: application/json" -d '{"scenario": "dev"}'
```

A reset clears proposals, threads, events and idempotency keys, resets Connects and the clock,
and restarts the seeded failure sequence. The rate limiter is cleared too.

### Advance time

```bash
curl -X POST localhost:8081/admin/tick -H "Authorization: Bearer $GIGSIM_ADMIN_TOKEN" -H "Content-Type: application/json" -d '{"hours": 24}'
```

Clients only react on ticks. A typical evaluation run: reset `dev`, submit proposals, tick 240
hours, read `GET /admin/stats`.

### Settings that matter

| setting (`gigsim/config.yaml`) | default | note |
|---|---|---|
| `rate_limit` | 30 burst, 0.5/s | per token, real seconds |
| `chaos.error_rate` | 0.02 | seeded 503s; set 0 for clean demos |
| `chaos.latency_ms_max` | 120 | real latency jitter |
| `clients.mode` | `rule_only` | `blended` adds an LLM judge (needs `OPENAI_API_KEY`) |
| `policy` | `v1` | switch live with `POST /admin/policy` |

### Tokens

Freelancer and admin tokens come from `GIGSIM_TOKEN_*` and `GIGSIM_ADMIN_TOKEN`; without them the
documented dev defaults apply. Never use the dev defaults on a public host.

### Frozen code

GigSim is tagged `gigsim-v1`. CI fails if anything under `gigsim/` differs from that tag, except
`gigsim/policies/` (the change request adds a policy file there) and `gigsim/data/`.

## MCP servers (Marketplace and Workspace)

Tool reference: [TOOLS.md](TOOLS.md). Both servers read `agent/config.yaml` (`mcp` section).

### Run over HTTP

GigSim must be running for the marketplace tools (`make gigsim`).

```bash
make mcp-marketplace
```

```bash
make mcp-workspace
```

They serve Streamable HTTP at `http://localhost:8101/mcp` and `http://localhost:8102/mcp`.
Every request needs `Authorization: Bearer <token>`. Tokens come from `MCP_TOKEN_AI_ML`,
`MCP_TOKEN_FULLSTACK` and `MCP_TOKEN_DATA_ANALYST`; the local dev defaults are
`dev-mcp-ai_ml`, `dev-mcp-fullstack` and `dev-mcp-data_analyst`. Missing or wrong tokens get 401.

### Open in MCP Inspector

HTTP (start the server first, then the Inspector):

```bash
npx @modelcontextprotocol/inspector
```

In the Inspector UI choose **Transport: Streamable HTTP**, URL `http://localhost:8101/mcp`
(workspace: `http://localhost:8102/mcp`), open **Authentication** and set the header
`Authorization` to `Bearer dev-mcp-ai_ml`, then **Connect** and open **Tools**.

stdio (the Inspector starts the server itself and it runs as `mcp.default_user`):

```bash
npx @modelcontextprotocol/inspector .venv/bin/python -m mcp_servers.marketplace.server
```

```bash
npx @modelcontextprotocol/inspector .venv/bin/python -m mcp_servers.workspace.server
```

Good screenshots for `docs/images/`: the tool list with annotations, `search_jobs` showing
`untrusted_text`, `submit_proposal` with `dry_run: true`, and the `marketplace_unavailable`
result with GigSim stopped.

### Audit logs and runtime files

- `data/audit/marketplace.jsonl`, `data/audit/workspace.jsonl`: append-only, one line per call,
  PII masked. Never edit or truncate them; rotate by moving the file aside.
- `data/workspace/<tenant>.json`: holds, email drafts and idempotency keys for the mock.
  Delete it to reset the mock calendar.

### Degraded mode

If GigSim is down, marketplace tools return `isError: true` with
`{"ok": false, "error": {"code": "marketplace_unavailable", "retry_after": 30}}` after the
adapter's bounded retries (3 retries, exponential backoff with jitter, `Retry-After` honoured).

## RAG index and Portfolio server

```bash
make db-up
```

Starts Postgres with pgvector (`infra/docker-compose.yml`, schemas `rag` and `langgraph` created
by `infra/postgres/init.sql`). `make db-down` stops it; data stays in the `pgdata` volume.

```bash
make index
```

Chunks and embeds every persona into `rag.chunks_<model>`. The first run downloads
nomic-embed-text v1.5 (about 550 MB) and takes about 1.5 minutes on CPU; later runs only embed
new or changed items (content hash). Install the embedder first with `uv sync --extra embed`.

```bash
make rag-eval VARIANT=v0
```

Writes `evals/results/rag_v0.json` (Recall@5, MRR, nDCG@10 per persona, latency, commit hash).

```bash
make mcp-portfolio
```

Serves `http://localhost:8103/mcp` (bearer token as for the other servers). In MCP Inspector use
Streamable HTTP with that URL and `Authorization: Bearer dev-mcp-ai_ml`, or over stdio:

```bash
npx @modelcontextprotocol/inspector .venv/bin/python -m mcp_servers.portfolio.server
```

Set `PORTFOLIO_DIR=/path/to/folder` to serve any folder of md, pdf and code instead of the personas.

## MCP client, GitHub ingest and the single-agent demo

Agents connect through `agent/mcp_client.py`. Server URLs come from `MCP_MARKETPLACE_URL`,
`MCP_PORTFOLIO_URL` and `MCP_WORKSPACE_URL` (defaults: local ports 8101, 8103, 8102) and the
bearer token of `mcp_client.user`.

GitHub ingest needs Docker and a fine-grained, read-only `GITHUB_TOKEN` in `.env`; list repos
under `rag.github_repos` (owner, repo, persona), then:

```bash
make index-github
```

It reads README and code through the official GitHub MCP server (read-only `repos` toolset),
indexes them with the same metadata and hashing as the personas, and writes
`evals/results/rag_github_index.json`. A later `make index` never deletes these items.

Single ReAct baseline (needs `GROQ_API_KEY` for the open-profile writer model and `make db-up`
with an index). It runs GigSim (dev scenario) and the MCP servers in-process:

```bash
make demo-single JOB=<job_id>
```

The run (tool calls, args, results, tokens, latency, final draft, dry-run preview and an
injection check for planted jobs) is saved to `evals/results/single_agent_demo.json`.

## Bid graph (analysis half)

Needs `make db-up` (portfolio index) and Ollama with `qwen3:4b` (`ollama pull qwen3:4b`); the
fallback model uses `GROQ_API_KEY`.

```bash
make scout PERSONA=ai_ml
```

Runs the saved searches from `scout.saved_searches` against an in-process GigSim (live scenario,
after a 72-hour tick) and prints jobs not seen before (`data/scout/seen.sqlite`).

```bash
make decision-eval
```

```bash
make decision-eval MODEL=qwen3:8b
```

Runs the bid graph on a stratified 90-job dev sample (30 per persona: 6 scams, 4 injections,
10 bid, 10 skip) and writes `evals/results/decisions_<model>.json`; add `FULL=1` for all 600 jobs.
LLM replies are cached in `data/cache/nodes/`, so reruns cost nothing. `make graph-render`
rewrites the diagram.

## Bid graph (proposal half, approval, durability)

Needs `make db-up` (pgvector and the `langgraph` checkpoint schema), Ollama with `qwen3:4b` and
`qwen3:8b`, and `GROQ_API_KEY` for the writer (`openai/gpt-oss-120b`; on a 429 it falls back to
local `qwen3:8b` straight away, because Groq's free tier caps tokens per day).

```bash
make crash-resume
```

Starts a thread for job `1c0b990bb7dbe947`, kills the process (SIGKILL) while it waits for
approval, restarts and approves, kills it again right after `submit_proposal` returns, restarts
once more, and checks GigSim: one submitted proposal, Connects charged once. Writes
`evals/results/crash_resume.json`; the GigSim database stays in `data/cache/crash_demo/<stamp>/`.

```bash
make replay THREAD=<thread_id> NODE=writer
```

Forks the thread from the checkpoint just before `NODE` and runs on against a scratch GigSim.

```bash
make proposal-eval
```

15 bid jobs (5 per persona) through writer, verifier, critic and compliance; an eval-only
auto-approver submits to an in-process GigSim (dev scenario, rule-only clients), ticks 168 hours
and records first replies. Writes `evals/results/proposals_<writer model>.json`.

Resuming a thread by hand (Python):

```python
await resume_job(thread_id, {"action": "edit", "edited_text": "..."}, ctx, graph)
await resume_job(thread_id, {"action": "reject", "reason": "budget too low"}, ctx, graph)
await resume_job(thread_id, {"action": "approve"}, ctx, graph)
```

A thread that fails `nodes.max_attempts` times gets status `dead_letter` with every error in
`errors`; a marketplace outage before approval or during submit gives status `queued`.

## API, conversation graph and memory

```bash
make db-up && make api       # http://localhost:8000/docs, log in as reviewer
make openapi                 # apps/api/openapi.json
```

A full approval cycle with curl:

```bash
TOKEN=$(curl -s -X POST localhost:8000/auth/login -H 'content-type: application/json' \
  -d '{"username":"reviewer","password":"reviewer-dev"}' | jq -r .access_token)
curl -s -X POST localhost:8000/jobs/scout -H "Authorization: Bearer $TOKEN"
curl -s -X POST localhost:8000/runs -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"job_id":"1c0b990bb7dbe947"}'
curl -sN localhost:8000/runs/1c0b990bb7dbe947:reviewer/events -H "Authorization: Bearer $TOKEN"
curl -s localhost:8000/approvals -H "Authorization: Bearer $TOKEN"
curl -s -X POST localhost:8000/approvals/1c0b990bb7dbe947:reviewer -H "Authorization: Bearer $TOKEN" \
  -H 'content-type: application/json' -d '{"action":"approve"}'
```

Client replies: `GET /messages`, then `POST /messages/{thread_id}/draft`; the draft appears in
`/approvals` with kind `conversation`. Style memory fills in from approval edits;
`GET /settings/memory` shows what was promoted and why, and `DELETE /settings/memory/style/<key>` forgets it.

## Deployment (Render free tier + Neon)

The public app is one container on Render's free web service: FastAPI serves the built web UI,
runs GigSim and the three MCP servers in-process, and uses Neon Postgres for everything durable.
Hugging Face Spaces was the first plan, but Docker Spaces on free CPU now need a PRO subscription.

- **Models:** `MODEL_PROFILE=open_hosted`, open-weight models on Groq (gpt-oss-20b with
  gpt-oss-120b as fallback for the small nodes; gpt-oss-120b with gpt-oss-20b as fallback for writer,
  critic and liaison). No Ollama in the deployment.
- **Embeddings:** the free tier has 512 MB, too little for torch. `EMBEDDINGS_PROVIDER=lite` embeds
  in the container with fastembed (ONNX) and `BAAI/bge-small-en-v1.5`, and the deployment searches its
  own Neon index built with that same embedder. nomic-embed-text-v1.5 (the main results) did not fit:
  through fastembed it peaks at 934 MB, and its quantized build only reaches cosine 0.962 to 0.973 with
  the torch vectors on 20 portfolio texts (0.99 was required). See `docs/rag_notes.md`.
- **Database:** `DATABASE_URL` is Neon's pooled URL. It holds the pgvector index (`rag` schema),
  LangGraph checkpoints and the store (users, threads, inbox, settings, memory). The pooler rejects
  startup `search_path` options, so on a pooled URL the LangGraph tables live in `public`.
  Index from a laptop: `DATABASE_URL=$NEON_DATABASE_URL make index`.
- **Deploy:** `python -m scripts.deploy_render` builds `infra/docker/Dockerfile.render` for
  linux/amd64, pushes it to Docker Hub, and creates or updates the `gigbid` service with secrets
  set through the Render API. It is built locally because `data/processed/` is git-ignored and the
  app needs `pricing_stats.json` and `scam_signals.json`. Needs `RENDER_API_KEY`,
  `DOCKERHUB_USERNAME` in `.env` (pushes with Docker Desktop's login).
- **Sleep and cold start:** free services sleep after 15 idle minutes. `.github/workflows/keepalive.yml`
  pings `/health` every 10 minutes once the `GIGBID_URL` repository variable is set. GitHub can
  delay scheduled runs, so a visitor may still hit a cold start of about a minute.
- **Reviewer:** user `reviewer`, persona ai_ml, password from the `REVIEWER_PASSWORD` secret.

### What resets on restart (ephemeral disk)

Durable in Neon: users, sessions (signed tokens), bid and conversation threads with their pending
approvals, the inbox, settings, style and outcome memory, and the portfolio index.

Reset on every restart or redeploy, because they are files on the container disk:
- **GigSim's state** (`data/api/stack/gigsim.db`): jobs reload from the seed, but proposals,
  Connects balances, client replies and simulated time start over. Old threads in Neon can then
  point at proposals the fresh GigSim no longer has. GigSim is frozen (`gigsim-v1`), so its storage
  cannot move to Postgres.
- **Scout seen-store** (sqlite): harmless, because the inbox in Neon already dedupes per job.
- **MCP audit logs** (JSONL) and the **LLM reply cache** (sqlite): lost; traces in LangSmith keep
  the same trace ids.

### Tracing

`LANGSMITH_TRACING=true` with `LANGSMITH_API_KEY` turns on LangSmith (project `gigbid`) through one
client that masks emails, phone numbers, card numbers, IBANs and payment links in every traced input
and output (`apps/api/tracing.py`). Each run and approval carries one trace id in the LangSmith
metadata and in the MCP audit logs. Shared example traces: `docs/TRACES.md`.

### Local full stack

`docker compose -f infra/docker-compose.yml up` starts the app on :8000, GigSim, the three MCP
servers over HTTP, Postgres with pgvector, a one-shot portfolio index, and Ollama (it pulls qwen3:4b
and qwen3:8b for the `open` profile). Secrets come from the environment. Redis is not used: the
scheduler is an in-process loop and checkpoints live in Postgres, so there is no Redis service.
