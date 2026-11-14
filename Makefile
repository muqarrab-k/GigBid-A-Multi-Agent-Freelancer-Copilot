.PHONY: install dev api test eval seed demo lint data synth gigsim gigsim-reset

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

seed:
	@echo "seed: not yet"

demo:
	@echo "demo: not yet"
