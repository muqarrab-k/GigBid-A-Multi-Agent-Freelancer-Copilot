.PHONY: install dev api test eval seed demo lint data synth gigsim gigsim-reset mcp-marketplace mcp-workspace snapshot-update

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

eval:
	@echo "eval: not yet"

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

snapshot-update:
	UPDATE_SNAPSHOTS=1 $(RUN) pytest -q tests/contract

seed:
	@echo "seed: not yet"

demo:
	@echo "demo: not yet"
