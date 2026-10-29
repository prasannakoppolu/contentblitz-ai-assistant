# Deployment Guide

## 1. Local (minimum requirement)

```bash
python -m venv .venv && source .venv/bin/activate   # Python 3.11+
pip install -r requirements.txt
cp .env.example .env                                   # optional keys
streamlit run src/web_app/streamlit_app.py             # http://localhost:8501
```

Offline demo: `CONTENTBLITZ_MOCK=1 streamlit run src/web_app/streamlit_app.py` or `make demo`.

## 2. Docker

```bash
docker compose up --build              # app on :8501, outputs on the contentblitz-data volume
docker compose --profile test run tests
```

The image runs as a non-root user, exposes a health check on `/_stcore/health`, and defaults to `APP_ENV=production`.

## 3. Streamlit Community Cloud

1. Push the repo to GitHub, then **New app** → main file `src/web_app/streamlit_app.py`.
2. In **Secrets**, add keys as TOML (`OPENAI_API_KEY = "sk-..."`, etc.) and `APP_ENV = "production"`.
   Streamlit exposes secrets as environment variables, which `load_settings()` reads.
3. Images are written to the ephemeral filesystem; export them from the UI.

## 4. Railway / Render / Fly.io

- Deploy from the Dockerfile; set env vars in the dashboard; expose port 8501.
- Mount a volume at `/data` to keep generated images.
- For persistent conversation memory install `langgraph-checkpoint-sqlite` and use `ContentBlitzEngine(memory="sqlite")`
  with the database on the volume, or use LangGraph's Postgres saver for multi-instance deployments.

## 5. Environments

| File | Used when | Highlights |
|---|---|---|
| `config/services.yaml` | always (base) | Fallback chains, model tiers, brand voice, app defaults |
| `config/development.yaml` | `APP_ENV=development` (default) | DEBUG logs, quick retries |
| `config/production.yaml` | `APP_ENV=production` | More retries, quality threshold 75, two refinement loops, `/data/outputs` |
| `config/test.yaml` | `APP_ENV=test` | Mock providers, no retries |

## 6. Monitoring & logging

- Structured logs on the `contentblitz` logger (`LOG_LEVEL`). Provider failures and retries are logged at WARNING.
- Usage/cost per session in the sidebar; `engine.usage()` exposes the same for scraping.
- Health: Docker `HEALTHCHECK` against Streamlit's health endpoint.
- Optional LangSmith tracing: `pip install langsmith` and set `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY`;
  LangGraph emits traces for every node automatically.

## 7. CI/CD

`.github/workflows/ci.yml` runs ruff and the full offline test suite (coverage gate 80%) on Python 3.11 and 3.12,
then builds the Docker image. Add a deploy job (e.g. Railway CLI or `docker push`) gated on the default branch.
