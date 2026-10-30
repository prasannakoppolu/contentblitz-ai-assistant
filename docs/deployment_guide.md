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
uvicorn as a non-root user, with a health check on `/api/health`. It defaults to `APP_ENV=production` and keeps
generated images and conversation memory (SQLite) on the `/data` volume.

## 3. Split hosting (optional)

The SPA is static: you can host `frontend/dist` on Vercel/Netlify/S3 and run the API elsewhere. Add your UI origin to
`allow_origins` in `create_app` (CORS) and proxy `/api` to the backend, or serve both from one origin as above
(simplest; SSE works without CORS).

## 4. Railway / Render / Fly.io

- Deploy from the Dockerfile; set env vars in the dashboard; expose port 8000.
- Mount a volume at `/data` to keep generated images.
- Conversation memory persists in `/data/contentblitz_memory.sqlite` (the image sets `CONTENTBLITZ_MEMORY=sqlite`).
  SQLite suits a single instance; for several replicas use LangGraph's Postgres saver (pass it as the registry's
  `checkpointer`).

## 5. Environments

| File | Used when | Highlights |
|---|---|---|
| `config/services.yaml` | always (base) | Fallback chains, model tiers, optional `models.openai.base_url`, brand voice, app defaults |
| `config/development.yaml` | `APP_ENV=development` (default) | DEBUG logs, quick retries |
| `config/production.yaml` | `APP_ENV=production` | More retries, quality threshold 75, two refinement loops, `/data/outputs` |
| `config/test.yaml` | `APP_ENV=test` | Mock providers, no retries |

## 6. Monitoring & logging

- Structured logs on the `contentblitz` logger (`LOG_LEVEL`). Provider failures and retries are logged at WARNING.
- Usage and estimated cost per provider configuration since start-up: Settings panel, or `POST /api/usage`.
- Health: `GET /api/health` (used by the Docker `HEALTHCHECK`).
- Behind nginx, disable response buffering for `/api/threads/*/chat` (the API already sends `X-Accel-Buffering: no`).
- LangSmith tracing (optional): set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` (project defaults to
  `contentblitz`). Every agent subgraph node, prompt and model call (with retries and fallbacks) appears as a trace;
  Settings shows whether tracing is on.
- Performance: `make bench` / `make bench-live` write latency, cost and quality reports to `docs/benchmarks/`.

## 7. CI/CD

`.github/workflows/ci.yml`: **frontend** (typecheck, Vitest, build), **backend** on Python 3.11 and 3.12 (ruff, full
offline pytest including Playwright browser e2e against the built UI, 80% coverage gate), then **docker** (build and
smoke-test the container). Add a deploy job (e.g. Railway CLI or `docker push`) gated on the default branch.
