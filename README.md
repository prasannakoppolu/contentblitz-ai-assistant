# ⚡ ContentBlitz: AI Content Marketing Assistant

A production-style **multi-agent content marketing system** built on **LangGraph**. Six specialised agents
research a topic with cited sources, turn it into a structured report, write SEO-optimised blog posts,
craft LinkedIn posts with a hashtag strategy and generate on-brand visuals. They work through a
conversational **React** interface (served by a FastAPI backend) with memory, quality scoring and multi-provider fallbacks.

> Capstone project: *Applied Agentic AI for SWEs: AI Content Marketing Assistant*.
> Runs **fully offline out of the box** (deterministic mock providers), so evaluators can try every feature
> without API keys. Add keys to switch to GPT-4o / Claude / Gemini, SERP API / Perplexity / Tavily and DALL-E 3 / Stability.

---

## ✨ Highlights

| Capability | What you get |
|---|---|
| **6 specialised agents** | Query Handler · Deep Research · Content Strategist · SEO Blog Writer · LinkedIn Writer · Image Generator |
| **Intelligent routing** | LLM router (cheap tier) with schema validation, plus a deterministic heuristic fallback; resolves follow-ups ("make it shorter", "turn *it* into a LinkedIn post") |
| **Research-first workflows** | Written content is automatically grounded in fresh research; research is reused across turns for the same topic |
| **Multi-provider fallbacks** | LLM: OpenAI → Claude → Gemini → mock · Research: SERP API → Perplexity → Tavily → mock · Images: DALL-E 3 → DALL-E 2 → Stability → local placeholder |
| **Resilience** | Exponential backoff with jitter, non-retryable auth errors, per-agent error isolation, graceful degradation |
| **Cost control** | 30-min TTL research cache, model tiers (mini for routing/meta/hashtags), usage & cost tracker in the UI |
| **SEO engine** | Keyword strategy, 1-2% density check, 150-160 char meta descriptions, H1/H2/H3 audit, internal-link suggestions, Flesch scores |
| **LinkedIn engine** | Hook-first templates, 1,300-1,600 character window, 8-12 hashtags, CTA detection, line-break optimisation |
| **Quality pipeline** | 0-100 scores per asset with sub-dimensions and suggestions; blogs below threshold are auto-refined |
| **Brand voice** | Configurable tone/audience/banned phrases, consistency checks, and **voice learning from sample content** |
| **Memory** | LangGraph checkpointer per conversation thread: in-memory by default, SQLite (`CONTENTBLITZ_MEMORY=sqlite`, the Docker default) to survive restarts; the browser remembers its conversation and restores it on reload |
| **Content series** | "Write a 3-part blog series about X" produces distinct, angle-driven parts |
| **Export** | Markdown · HTML · Plain text · PDF · WordPress WXR (CMS import) · scheduler JSON (Buffer/Hootsuite) · PNG |
| **Web UI** | React + TypeScript (Vite): chat with a live six-station agent pipeline, content editor with instant re-scoring, research panel with linked citations, exports, settings; responsive, dark mode |
| **Testing** | 129 Python tests (unit / API / integration / e2e incl. real-browser Playwright), **95% coverage**, plus 16 Vitest component tests; CI on Python 3.11 & 3.12 |

---

## 🏗️ Architecture

```mermaid
flowchart LR
    U([User]) --> UI[React UI<br/>Chat · Content · Research · Export]
    UI -- REST + SSE --> API[FastAPI<br/>src/api/server.py]
    API --> E[ContentBlitzEngine]
    E --> G{{LangGraph StateGraph<br/>+ checkpointer memory}}
    G --> QH[Query Handler]
    QH -->|next_step| R[Deep Research]
    R --> CS[Content Strategist]
    CS --> B[SEO Blog Writer]
    B --> L[LinkedIn Writer]
    L --> I[Image Generator]
    I --> F[Finalize]
    QH -.skip / subset.-> B & L & I & F
    subgraph Services [Service abstraction layer]
      LLM[LLM chain<br/>OpenAI → Claude → Gemini → Mock]
      S[Research chain<br/>SERP → Perplexity → Tavily → Mock]
      IMG[Image chain<br/>DALL-E 3 → DALL-E 2 → Stability → Placeholder]
      C[(TTL cache)]
      T[(Usage tracker)]
    end
    R & CS & B & L & I & QH --- Services
```

The Query Handler produces a **plan** (an ordered subset of agents). After every node, the router function
`next_step` picks the next unfinished agent, so a single graph handles every workflow: research-only,
blog-only, image-only, refinements and full campaigns. See [docs/architecture.md](docs/architecture.md) and the
[technical design](docs/technical_design.md).

### Project structure

```
contentblitz/
├── src/
│   ├── agents/              # The six agents (+ base class)
│   │   ├── query_handler.py   research_agent.py   content_strategist.py
│   │   └── blog_writer.py     linkedin_writer.py  image_generator.py
│   ├── core/                # config.py, router.py, workflow.py (engine facade), resilience.py
│   ├── integrations/        # Provider adapters + fallback chains
│   │   ├── base.py  openai_client.py  llm_clients.py (Claude, Gemini)
│   │   ├── serp_client.py  perplexity_client.py (Perplexity, Tavily)
│   │   ├── image_clients.py (Stability, placeholder)  mock_client.py  service_factory.py
│   ├── utils/               # content_optimization.py, quality_validation.py, templates.py, export_tools.py
│   ├── workflow/            # langgraph_workflow.py, state_management.py
│   ├── api/                 # FastAPI: REST + Server-Sent Events, serves the built UI
│   └── cli.py
├── frontend/                # React + TypeScript (Vite): src/components, src/api.ts, tests
├── tests/{unit,integration,e2e}/
├── config/{services,development,production,test}.yaml
├── docs/                    # architecture, API, deployment, technical design, service comparison, demo script
├── Dockerfile  docker-compose.yml  Makefile  requirements*.txt  .env.example
└── .github/workflows/ci.yml
```

---

## 🚀 Quick start

```bash
git clone https://github.com/prasannakoppolu/contentblitz-ai-assistant.git
cd contentblitz-ai-assistant
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
(cd frontend && npm ci && npm run build)        # Node 20+

# Option A: offline demo (no keys, no cost)
CONTENTBLITZ_MOCK=1 uvicorn src.api.server:app --port 8000

# Option B: real providers
cp .env.example .env     # add any keys you have; missing ones are skipped
uvicorn src.api.server:app --port 8000
```

Open http://localhost:8000. API keys can also be pasted into Settings; they stay in that browser tab's memory only.

**Frontend development (hot reload):** run `make api` (FastAPI on :8000) and `make web` (Vite on :5173, proxying
`/api`), then open http://localhost:5173.

**Docker:** `docker compose up --build` (reads `.env` if present).
**Terminal:** `python -m src.cli --interactive --mock`.
**Tests:** `make dev`, then `pytest --cov` (Python, incl. browser e2e once the UI is built) and `make test-ui` (Vitest + typecheck).

### Environment variables

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | GPT-4o / GPT-4o-mini and DALL-E 3/2 |
| `ANTHROPIC_API_KEY` | Claude Sonnet / Haiku (LLM fallback #1) |
| `GOOGLE_API_KEY` | Gemini 2.0 Flash (LLM fallback #2) |
| `SERPAPI_API_KEY` · `PERPLEXITY_API_KEY` · `TAVILY_API_KEY` | Research engines |
| `STABILITY_API_KEY` | Stable Image Core (image fallback) |
| `APP_ENV` | `development` / `production` / `test`: selects `config/<env>.yaml` |
| `CONTENTBLITZ_MOCK` | `1` forces offline mode |
| `CONTENTBLITZ_OUTPUT_DIR` | Where images and metadata are saved (default `outputs/`) |
| `CONTENTBLITZ_MEMORY` | `memory` (default) or `sqlite` to keep conversations across server restarts |
| `CONTENTBLITZ_MEMORY_PATH` | SQLite file for conversation memory (default `contentblitz_memory.sqlite`; Docker: `/data/...`) |
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` |

---

## 💬 Usage examples

| You say | Agents that run | Result |
|---|---|---|
| *Research the latest trends in sustainable packaging for e-commerce* | QH → Research → Strategist | Trend report with 10 cited sources, stats, angles, keyword ideas |
| *Now write an SEO blog post about it* | QH → Blog (research reused) | ~1,500-word article, meta description, SEO + quality scores |
| *Make it shorter* | QH → Blog (refine) | Revision 2, re-scored |
| *Turn it into a LinkedIn post* | QH → LinkedIn | 1,300-1,600 chars, 8-12 hashtags, hook + CTA |
| *Create an image for the LinkedIn post* | QH → Image | Enhanced prompt → DALL-E 3 (or fallback), saved PNG + metadata |
| *Create a campaign about B2B podcast marketing* | All six | Report, blog, LinkedIn post and image in one turn |
| *Write a 3-part blog series about zero-party data* | QH → Research → Blog | Three distinct articles + WordPress XML export |
| *Write a listicle: 7 ways to improve email open rates* | QH → Research → Blog | Listicle template applied |
| *Give me a competitive analysis of project management tools* | QH → Research → Strategist | Competitive-analysis report template |

Programmatic use:

```python
from src.core.config import load_settings
from src.core.workflow import ContentBlitzEngine

engine = ContentBlitzEngine(load_settings())
state = engine.run("Create a campaign about urban beekeeping", thread_id="acme")
print(state["response"])
print(state["blog"]["quality"]["score"], state["linkedin"]["hashtags"], state["image"]["path"])
state = engine.run("make the LinkedIn post more casual", thread_id="acme")   # memory-aware follow-up
```

Full agent inputs/outputs and the HTTP API are documented in [docs/api_documentation.md](docs/api_documentation.md);
the live OpenAPI docs are at http://localhost:8000/docs.

---

## 🔁 Error handling & fallbacks

1. **Within a provider:** HTTP 429/5xx/network errors retry with exponential backoff and jitter; 401/403/4xx fail fast.
2. **Across providers:** `ProviderChain` moves to the next provider and records each attempt (shown in the UI).
3. **Within an agent:** research falls back to an extractive summary if every LLM fails; writers fall back to
   research keywords if keyword generation fails; image prompt enhancement falls back to a template.
4. **Across agents:** each LangGraph node is wrapped, so a failed agent is reported in the reply while the rest
   still deliver. Dependants (the strategist after failed research) are skipped cleanly.
5. **Last resort:** mock LLM/search and the local placeholder renderer keep the app usable during a full outage.

## 💰 Performance & cost tips

- Research results are cached for 30 minutes by query. Repeat topics cost nothing.
- Routing, meta descriptions, hashtags and image prompts use the **fast** tier (GPT-4o-mini / Haiku / Flash);
  long-form writing uses **premium**. Edit tiers in `config/services.yaml`.
- Research for a topic is **reused across turns**, so a follow-up blog/LinkedIn post doesn't re-search.
- `max_refinement_loops` caps automatic rewrites (1 in dev, 2 in prod).
- Settings → **Usage since the server started** shows API calls, estimated cost, cache hits and the active writing chain
  for your provider configuration (`POST /api/usage` returns the full breakdown, including tokens).
- For development, Gemini Flash's free tier plus Tavily's free tier is the cheapest live configuration.

## 🛠️ Troubleshooting

| Symptom | Fix |
|---|---|
| Banner says *offline demo mode* | Offline mode is on (the default when the server has no keys). Add keys to `.env` or Settings → API keys, then untick **Offline demo mode** in Settings. |
| Page says *ContentBlitz can't reach its server* | The API isn't running (or not on :8000 for `make web`). Start it with `uvicorn src.api.server:app --port 8000`. |
| `{"detail":"Not Found"}` at http://localhost:8000/ | The UI isn't built. Run `cd frontend && npm ci && npm run build`, then restart the server. |
| Agent progress arrives all at once behind a proxy | Disable response buffering for `/api/threads/*/chat` (see the deployment guide). |
| Image shows a gradient card | All image providers failed or no key; check the *Provider attempts* table in Content → Image. |
| `auth error 401` in the trace | Invalid key: auth errors are not retried, so the next provider is used. Fix the key. |
| `rate limited (429)` warnings | Handled automatically with backoff; reduce concurrency or add another provider. |
| Follow-up applied to the wrong piece | Name it explicitly: *"make the **blog** shorter"*. |
| PDF export unavailable | `pip install reportlab`. |
| Conversation gone after a server restart | Set `CONTENTBLITZ_MEMORY=sqlite` (already set in Docker). |

## 📚 Documentation

- [Architecture](docs/architecture.md): components, data flow, state model, sequence diagrams
- [Technical design](docs/technical_design.md): decisions, trade-offs, fallback patterns, quality pipeline, scalability
- [API documentation](docs/api_documentation.md): every agent's inputs/outputs, engine & provider interfaces
- [Service comparison](docs/service_comparison.md): providers, cost-benefit, recommendations by budget
- [Deployment guide](docs/deployment_guide.md): local, Docker, Railway/Render/Fly, monitoring
- [Demo script](docs/demo_script.md): the walkthrough to record for the submission video

## 🧭 Roadmap (stretch)

CMS publishing (WordPress REST / Ghost / Medium) on top of the existing WXR export, Buffer/Hootsuite scheduling via
the scheduler JSON payload, LangSmith tracing, and fine-tuned brand-voice models.
