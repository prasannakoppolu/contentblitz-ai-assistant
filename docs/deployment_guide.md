# Deployment Guide

## 1. Local (minimum requirement)

```bash
python -m venv .venv && source .venv/bin/activate   # Python 3.11+
pip install -r requirements.txt
(cd frontend && npm ci && npm run build)             # Node 20+
cp .env.example .env                                   # optional keys
uvicorn src.api.server:app --port 8000                 # http://localhost:8000 (UI + API)
```

Offline demo: `make demo`. Frontend hot reload: `make api` + `make web` → http://localhost:5173.

## 2. Docker

```bash
docker compose up --build              # UI + API on :8000, outputs on the contentblitz-data volume
```

The multi-stage image builds the React app with Node, then copies `frontend/dist` into a slim Python image that runs
uvicorn as a non-root user, with a health check on `/api/health`. It defaults to `APP_ENV=production`.

## 3. Split hosting (optional)

The SPA is static: you can host `frontend/dist` on Vercel/Netlify/S3 and run the API elsewhere. Add your UI origin to
`allow_origins` in `create_app` (CORS) and proxy `/api` to the backend, or serve both from one origin as above
(simplest; SSE works without CORS).

## 4. Railway / Render / Fly.io

- Deploy from the Dockerfile; set env vars in the dashboard; expose port 8000.
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
- Health: `GET /api/health` (used by the Docker `HEALTHCHECK`).
- Behind nginx, disable response buffering for `/api/threads/*/chat` (the API already sends `X-Accel-Buffering: no`).
- Optional LangSmith tracing: `pip install langsmith` and set `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY`;
  LangGraph emits traces for every node automatically.

## 7. CI/CD

`.github/workflows/ci.yml`: **frontend** (typecheck, Vitest, build), **backend** on Python 3.11 and 3.12 (ruff, full
offline pytest including Playwright browser e2e against the built UI, 80% coverage gate), then **docker** (build and
smoke-test the container). Add a deploy job (e.g. Railway CLI or `docker push`) gated on the default branch.
