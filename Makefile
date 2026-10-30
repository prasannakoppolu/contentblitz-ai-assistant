.PHONY: install dev ui api web demo test test-ui cov cli docker lint bench bench-live

install:        ## Python + frontend dependencies
	pip install -r requirements.txt
	cd frontend && npm ci
dev:            ## Dev/test tooling (incl. Playwright browser)
	pip install -r requirements-dev.txt && playwright install chromium
	cd frontend && npm ci
ui:             ## Build the React app into frontend/dist
	cd frontend && npm run build
api:            ## API with auto-reload on :8000 (pair with `make web`)
	uvicorn src.api.server:app --reload --port 8000
web:            ## Vite dev server on :5173 with hot reload (proxies /api to :8000)
	cd frontend && npm run dev
demo: ui        ## Build the UI and serve everything offline on :8000
	CONTENTBLITZ_MOCK=1 uvicorn src.api.server:app --port 8000
test:           ## Python tests (browser e2e runs when frontend/dist exists)
	pytest
test-ui:        ## Frontend unit tests + typecheck
	cd frontend && npm test && npm run typecheck
cov:
	pytest --cov --cov-report=term-missing
cli:            ## Interactive terminal chat (offline)
	python -m src.cli --interactive --mock
bench:          ## Offline benchmark -> docs/benchmarks/offline-mock.md
	python -m scripts.benchmark --mock
bench-live:     ## Benchmark with your keys: make bench-live LABEL=balanced ARGS="--llm openai"
	python -m scripts.benchmark --label $(or $(LABEL),live) $(ARGS)
docker:
	docker compose up --build
lint:
	ruff check src tests scripts
