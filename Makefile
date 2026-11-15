.PHONY: install dev api test eval eval-record check-repo demo-gif seed demo lint data synth gigsim gigsim-reset mcp-marketplace mcp-workspace mcp-portfolio snapshot-update db-up db-down index rag-eval index-github demo-single scout decision-eval graph-render replay crash-resume proposal-eval openapi web web-build web-client e2e api-fake

VARIANT ?= v0
COMPOSE := docker compose -f infra/docker-compose.yml

UV := $(shell command -v uv 2>/dev/null)
ifdef UV
RUN := uv run
else
RUN :=
endif

install:
ifdef UV
	uv sync --extra dev --extra data
else
	python -m pip install -e ".[dev,data]"
endif

dev: api

api:
	$(RUN) uvicorn apps.api.main:app --reload --port 8000

test:
	$(RUN) pytest -q

lint:
	$(RUN) ruff check .

# keyless smoke eval, writes evals/results/smoke_eval.json
eval:
	$(RUN) python -m evals.runners.smoke_eval

eval-record:
	$(RUN) python -m evals.runners.smoke_eval --record

check-repo:
	$(RUN) python -m scripts.check_repo

data:
	$(RUN) python -m data_pipeline.run

synth:
	$(RUN) python -m synth.run

gigsim:
	$(RUN) uvicorn gigsim.app:create_app --factory --port 8081

gigsim-reset:
	$(RUN) python -m gigsim.reset --scenario live

mcp-marketplace:
	$(RUN) python -m mcp_servers.marketplace.server --http

mcp-workspace:
	$(RUN) python -m mcp_servers.workspace.server --http

mcp-portfolio:
	$(RUN) python -m mcp_servers.portfolio.server --http

db-up:
	$(COMPOSE) up -d --wait postgres

db-down:
	$(COMPOSE) stop postgres

index:
	$(RUN) python -m rag.ingest.run

index-github:
	$(RUN) python -m rag.ingest.run --github

demo-single:
	$(RUN) python -m agent.baselines.demo $(JOB)

scout:
	$(RUN) python -m agent.nodes.scout --persona $(or $(PERSONA),ai_ml)

decision-eval:
	$(RUN) python -m evals.runners.decision_eval $(if $(MODEL),--cheap-model $(MODEL)) $(if $(FULL),--full)

graph-render:
	$(RUN) python -m agent.graphs.render

rag-eval:
	$(RUN) python -m evals.runners.rag_eval --variant $(VARIANT)

snapshot-update:
	UPDATE_SNAPSHOTS=1 $(RUN) pytest -q tests/contract

seed:
	@echo "seed: not yet"

demo:
	@echo "demo: not yet"

replay:
	$(RUN) python -m agent.graphs.replay $(THREAD) $(NODE)

crash-resume:
	$(RUN) python -m scripts.crash_resume_demo

proposal-eval:
	$(RUN) python -m evals.runners.proposal_eval

openapi:
	$(RUN) python -m apps.api.export_openapi

web-client: openapi
	cd apps/web && npm run client

web:
	cd apps/web && npm run dev

web-build:
	cd apps/web && npm install && npm run build

# api with the fake model, in-process gigsim; no keys
api-fake:
	GIGBID_FAKE_LLM=1 $(RUN) uvicorn apps.api.main:app --port 8000

e2e: web-build
	cd apps/web && npx playwright install chromium && npx playwright test; echo "report: apps/web/playwright-report/index.html"

# readme gif from the approve e2e test
demo-gif: web-build
	cd apps/web && npx playwright test -c playwright.demo.config.ts -g "approve submits once"
	python -m scripts.make_demo_gif
