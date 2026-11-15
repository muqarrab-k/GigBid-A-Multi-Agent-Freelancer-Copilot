# GigBid API

FastAPI backend over the bid graph, the conversation graph and long-term memory. Every route
except `/health` and `/auth/*` needs a bearer token, and every query is scoped to the signed-in
user (threads, inbox, settings and memory live under that username in the LangGraph store).

## Run locally

```bash
make db-up        # postgres + pgvector (checkpoints, store, rag index)
make index        # portfolio index, once
make api          # uvicorn on :8000, docs at http://localhost:8000/docs
```

- `api.mcp: local` (default) runs GigSim (dev scenario, `data/api/stack/`) and the three MCP
  servers in this process, so nothing else needs to be started. `remote` talks to the MCP servers
  over HTTP (`make gigsim`, `make mcp-marketplace`, ...).
- Checkpoints and memory go to Postgres (`checkpointer.backend`, `memory.backend`), so pending
  approvals survive a restart.
- Reviewer account: `reviewer` with the `ai_ml` persona, password from `REVIEWER_PASSWORD`
  (dev default `reviewer-dev`). Tokens are signed with `APP_SECRET_KEY`; if it is unset, a random
  key is used and tokens end at restart.
- `make openapi` writes `apps/api/openapi.json` for the web client generator.

## Endpoints

| method | path | what |
|---|---|---|
| POST | `/auth/login` | `{username, password}` -> bearer token |
| POST | `/auth/register` | `{username, password, persona}`; the persona picks the MCP user |
| GET | `/auth/me` | current user |
| GET | `/jobs` | inbox ranked by fit: risk badges, recommended action, price, Connects cost |
| POST | `/jobs/scout?analyse=` | run the saved searches now; `analyse=true` also starts bid runs |
| GET | `/jobs/{job_id}` | JobSpec, risk report, requirement-to-evidence matrix, price rationale, decision reasons |
| POST | `/runs` | `{job_id}`: start a bid run, thread id `<job_id>:<username>`; idempotent |
| GET | `/runs/{thread_id}` | status, next node, trace id |
| GET | `/runs/{thread_id}/events` | SSE, node by node; ends with `approval_required` and `done` |
| GET | `/approvals` | pending approvals read from the checkpointer (bid and conversation) |
| POST | `/approvals/{thread_id}` | `{action: approve \| edit \| reject, edited_text?, reason?}` resumes the thread |
| GET | `/proposals` | proposals from the marketplace, linked to their thread |
| GET | `/pipeline` | status counts; new GigSim events also feed outcome memory |
| GET | `/messages` | client threads with their draft status |
| GET | `/messages/{thread_id}` | messages (client text marked untrusted), intent, flags, pending draft |
| POST | `/messages/{thread_id}/draft` | run the conversation graph up to its approval interrupt |
| GET | `/analytics` | reply and hire rate by category, Connects by outcome, cost and latency per proposal, top rejection reasons, eval files |
| GET, PUT | `/settings` | autonomy (auto-send is always false), budgets, saved searches |
| GET | `/settings/memory` | promoted style and outcome memory, each with its rule and sources |
| DELETE | `/settings/memory/{kind}/{key}` | forget one item |
| GET | `/status` | marketplace up or down, for the degraded banner |
| POST | `/jobs/{job_id}/skip` | hide a job from the inbox |
| POST | `/portfolio/upload` | `{filename, text, type}`: one .md or .txt file into the user's index (`index_new_work`, never deletes) |

## Web UI and test mode

`make web-build` builds `apps/web/dist`; the API then serves it at `/`. A browser page load
(`Accept: text/html`) gets `index.html`, an API call to the same path gets JSON, so one URL and one
container work. `GIGBID_FAKE_LLM=1` (`make api-fake`) swaps in a scripted model, fake embeddings,
an in-process GigSim and memory checkpoints, and adds `POST /test/marketplace {down}` to simulate an
outage; it is what the Playwright tests run against. Never set it in production.

## Scheduler

`apps/api/scheduler.py` is the lightweight worker: an asyncio loop in the API process
(`api.scheduler.enabled`, every `interval_minutes`) that runs each user's saved searches and starts a
bid run for each new job. It is idempotent per job: one inbox entry and one thread per job and user.
