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
