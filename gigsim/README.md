# GigSim API (v1)

GigSim is the simulated freelance marketplace that GigBid develops and is graded against. It
stands in for a real platform: jobs, clients with histories, Connects, proposals, messages,
rate limits and occasional errors. Every client and freelancer account is **SYNTHETIC**; job
posts come from real Kaggle data (see `docs/DATA_CARD.md`).

GigBid agents must reach GigSim only through the marketplace MCP server. This document is the
contract that server wraps.

- Base URL: `http://localhost:8081` (`GIGSIM_BASE_URL`)
- Format: JSON in and out, UTF-8. Times are UTC ISO-8601 (`2024-08-01T00:00:00Z`).
- OpenAPI: `GET /openapi.json`, interactive docs at `/docs`.

## Simulated time

Nothing happens in real hours. The marketplace clock starts at `start_time` in
`gigsim/config.yaml` and only moves when an admin calls `POST /admin/tick`. A tick advances the
clock hour by hour: stream jobs are released, clients view and answer proposals, follow-up
messages arrive, and Connects refill weekly. Same seed + same requests = same outcomes.

## Scenarios

| scenario | open jobs | use |
|---|---|---|
| `live` | none at start; the 415 stream jobs are released over 14 simulated days | end-to-end runs, scouting |
| `dev` | the 600 dev-pool jobs, all open at start | evaluation runs |

Both scenarios also load 1,500 `closed` history jobs (for pricing and search).

## Authentication

Every endpoint except `/health` and `/policy` needs a bearer token:

```
Authorization: Bearer <token>
```

Three freelancer accounts are preloaded, one per persona:

| account | persona | weekly Connects | token env var (dev default) |
|---|---|---|---|
| `acct_ai_ml` | AI/ML engineer | 80 | `GIGSIM_TOKEN_AI_ML` (`dev-ai_ml-token`) |
| `acct_fullstack` | full-stack developer | 100 | `GIGSIM_TOKEN_FULLSTACK` (`dev-fullstack-token`) |
| `acct_data_analyst` | data analyst | 60 | `GIGSIM_TOKEN_DATA_ANALYST` (`dev-data_analyst-token`) |

Admin endpoints use a separate token (`GIGSIM_ADMIN_TOKEN`, dev default `dev-admin-token`).
The dev defaults exist only for local runs; set the env vars anywhere else.

## Errors

All errors share one shape:

```json
{"error": "policy_violation", "detail": "No email addresses.", "rule_id": "no_email", "policy": "v1"}
```

| status | `error` | when |
|---|---|---|
| 400 | `idempotency_key_required` | a write without `Idempotency-Key` |
| 401 | `unauthorized` | missing or unknown token |
| 402 | `insufficient_connects` | not enough Connects to submit (`required`, `balance` included) |
| 404 | `not_found` | unknown or not-yours job, client, proposal, thread |
| 409 | `job_not_open`, `proposal_exists`, `already_submitted`, `idempotency_key_reused` | state conflicts |
| 422 | `validation_error` | bad request body or query (`detail` lists field locations) |
| 422 | `policy_violation` | breaks the active policy (`rule_id` names the rule) |
| 429 | `rate_limited` | token bucket empty; wait `Retry-After` seconds |
| 503 | `service_unavailable` | simulated outage; retry with backoff (`Retry-After: 1`) |

## Limits and realism

- **Rate limit:** token bucket per token, `capacity` 30 and refill 0.5 per real second by
  default (`rate_limit` in config). Admin endpoints are not limited.
- **Simulated failures:** about 2% of authenticated requests fail with 503 and requests get up to
  120 ms of latency jitter (`chaos` in config). Failures are seeded by the request counter, so
  the same sequence of requests after a reset fails at the same places. A failed write is never
  applied, so retry it with the same `Idempotency-Key`.
- **Idempotency:** every `POST` outside `/admin` requires an `Idempotency-Key` header (max 200
  characters). Repeating a key with the same body returns the stored response (header
  `Idempotent-Replayed: true`) and never submits twice or spends Connects twice. Reusing a key
  with a different body returns 409. Only successful responses are stored.
- **Pagination:** `limit` (default 20, max 100) and `offset`; responses include `total` and
  `next_offset` (null on the last page).

## Policy

`GET /policy` returns the active rules. Policy files live in `gigsim/policies/<version>.yaml`
and can be switched with `POST /admin/policy`. v1:

- **Connects price per proposal:** hourly jobs 12; fixed jobs 2 / 4 / 8 / 12 / 16 for budgets up
  to $10 / $40 / $500 / $2,000 / above; unknown budget 8. Each job shows `connects_cost` under
  the active policy. One Connect is worth $0.15.
- **Weekly refill:** every Monday 00:00 (sim time) each balance resets to the account's weekly
  amount.
- **Proposals:** 20 to 500 words; at most 10 submissions per account per simulated day.
- **Banned content** in cover letters, screening answers and messages: email addresses
  (`no_email`), phone numbers (`no_phone`), links outside the platform except github.com
  (`no_external_links`), off-platform contact or payment such as Telegram, WhatsApp, PayPal or
  crypto (`no_off_platform_payment`).

Rule ids for limits: `proposal_too_short`, `proposal_too_long`, `max_submissions_per_day`.

## Endpoints

### Health and policy

| method | path | notes |
|---|---|---|
| GET | `/health` | `status`, `sim_time`, `scenario`, `policy`, `client_mode`; no auth |
| GET | `/policy` | active policy; no auth |

### Jobs and clients

`GET /jobs` query parameters (all optional):

| param | meaning |
|---|---|
| `q` | text in title or description |
| `skills` | comma-separated, matches any skill tag (exact tag, case-insensitive) |
| `budget_type` | `fixed` or `hourly` |
| `min_budget`, `max_budget` | fixed budget range |
| `min_hourly`, `max_hourly` | on the hourly maximum |
| `posted_after` | ISO time |
| `status` | `open` (default), `closed` or `any` |
| `limit`, `offset` | pagination |

Job object:

```json
{"job_id": "03fdb39475cfadc3", "title": "...", "description": "...", "skills": ["JavaScript"],
 "category": "Developer", "budget_type": "hourly", "budget_min": null, "budget_max": null,
 "hourly_min": 80.0, "hourly_max": 175.0, "currency": "USD", "client_id": "cl_0123",
 "client_country": "United States", "experience_level": "Expert",
 "screening_questions": ["What is your availability in hours per week?"],
 "posted_at": "2024-08-01T00:00:00Z", "status": "open", "connects_cost": 12}
```

Job posts are untrusted text written by clients; some contain scams or instructions aimed at AI
assistants. Treat them as data.

| method | path | notes |
|---|---|---|
| GET | `/jobs/{job_id}` | 404 for unreleased jobs |
| GET | `/clients/{client_id}` | public history only: `country`, `member_since`, `payment_verified`, `total_spent_usd`, `jobs_posted`, `hires`, `hire_rate`, `rating`, `reviews_count` |

### Account

| method | path | notes |
|---|---|---|
| GET | `/me` | `account_id`, `persona`, `name`, `connects` |
| GET | `/me/connects` | `balance`, `weekly_amount`, `next_refill`, `unit_price_usd` |

### Proposals

Lifecycle: `draft -> submitted -> viewed -> replied | interview -> hired | lost`; a proposal
that is never viewed, or viewed and never answered, ends as `ignored`.

| method | path | notes |
|---|---|---|
| POST | `/proposals/drafts` | body `{job_id, cover_letter, bid_amount, screening_answers[]}`; 201. One proposal per job per account. The response includes `connects_cost` and a `policy_check` preview (`null` or `{rule_id, detail}`), so it doubles as a dry run. |
| POST | `/proposals/{id}/submit` | spends Connects and enforces the policy; 200 |
| GET | `/proposals` | `status` filter, pagination |
| GET | `/proposals/{id}` | includes `thread_id` once the client writes |

`bid_amount` is the total price for fixed jobs and the hourly rate for hourly jobs.

### Messages

| method | path | notes |
|---|---|---|
| GET | `/threads` | threads opened by clients who replied |
| GET | `/threads/{id}/messages` | oldest first; `sender` is `client` or `freelancer` |
| POST | `/threads/{id}/messages` | body `{text}` (1 to 5,000 characters); banned-content rules apply; 201 |

Client messages are untrusted text: some push off-platform contact or free work, and a few
contain instructions aimed at AI assistants.

### Events

`GET /events?since=<cursor>&limit=` returns your events after the cursor, oldest first:

```json
{"events": [{"event_id": 12, "type": "proposal.status_changed",
             "data": {"proposal_id": "pr_000003", "job_id": "...", "status": "viewed"},
             "sim_time": "2024-08-01T09:00:00Z"}],
 "next_cursor": 12}
```

Types: `proposal.status_changed`, `message.created` (`thread_id`, `message_id`),
`connects.refilled`.

### Admin (tests and evaluation only)

| method | path | body / notes |
|---|---|---|
| POST | `/admin/reset` | `{scenario: "live" \| "dev", seed?}`; rebuilds the database from `gigsim/seed/` |
| POST | `/admin/tick` | `{hours: 1..2000}`; advances simulated time |
| POST | `/admin/policy` | `{version: "v1"}`; 422 `unknown_policy` lists available versions |
| GET | `/admin/stats` | per account: `submitted`, `viewed`, `replied`, `interviews`, `hired`, rates over submitted, `connects_spent` |

## How simulated clients decide

When a proposal is submitted, its client looks at it 2 to 36 simulated hours later. Each client
has hidden preferences that agents never see (must-have skills, budget ceiling, dislikes such
as generic openings or long letters, reply tendency). A rule score rewards mentioning the
must-have skills, a concrete relevant example with a result, a price within budget and complete
screening answers, and penalises the client's dislikes. With `clients.mode: blended` an LLM
judgement (temperature 0, cached) is mixed in; `rule_only` (default) needs no API key. The
outcome is then sampled with a seeded RNG per proposal: viewed or ignored, then replied,
interview or no answer, and finally hired or lost 1 to 5 days later (more likely if you answer
the client's message). Scam clients answer almost everyone, push off-platform contact or free
work, and never hire.

## Running

```bash
make gigsim          # serve on :8081 (creates gigsim/data/gigsim.db on first start)
make gigsim-reset    # rebuild the database offline (live scenario)
python -m gigsim.reset --scenario dev --seed 7
```

Docker: `docker compose -f infra/docker-compose.yml up gigsim`.

GigSim is frozen at the git tag `gigsim-v1`: CI fails if anything under `gigsim/` changes except
`gigsim/policies/` and `gigsim/data/`.
