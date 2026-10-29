.PHONY: install dev test cov run demo cli docker lint

install:        ## Install runtime deps
	pip install -r requirements.txt
dev:            ## Install dev deps
	pip install -r requirements-dev.txt
test:           ## Run all tests (offline)
	pytest
cov:            ## Tests with coverage report
	pytest --cov --cov-report=term-missing
run:            ## Start the Streamlit app
	streamlit run src/web_app/streamlit_app.py
demo:           ## Start the app in offline demo mode
	CONTENTBLITZ_MOCK=1 streamlit run src/web_app/streamlit_app.py
cli:            ## Interactive terminal chat (offline)
	python -m src.cli --interactive --mock
docker:         ## Build and run with Docker
	docker compose up --build
lint:
	ruff check src tests
