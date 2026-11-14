.PHONY: install dev api test eval seed demo lint

UV := $(shell command -v uv 2>/dev/null)
ifdef UV
RUN := uv run
else
RUN :=
endif

install:
ifdef UV
	uv sync --extra dev
else
	python -m pip install -e ".[dev]"
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

seed:
	@echo "seed: not yet"

demo:
	@echo "demo: not yet"
