# Architecture

ContentBlitz is a multi-agent content marketing system: a React single-page app talks to a FastAPI server, which runs a
**LangGraph** supervising graph whose six agents are each **LangGraph subgraphs** calling **LangChain** chat models.
This document goes from the outside in (C4 style), then covers the graphs, the LLM call path, the main request flows,
state, deployment and quality attributes. The reasoning behind the major choices is recorded as ADRs in
[`docs/adr/`](adr/README.md).

| Level | Diagram | What it answers |
|---|---|---|
| 1 | [System context](#1-system-context) | Who uses ContentBlitz and which external services it depends on |
| 2 | [Containers](#2-containers) | The deployable/runtime pieces and how they communicate |
| 3 | [Backend components](#3-backend-components) | Modules inside the API server and their dependencies |
| 4 | [Supervising graph](#4-supervising-graph) and [agent subgraphs](#5-agent-subgraphs) | How a request moves through the agents |
| – | [LLM call path](#6-llm-call-path-retries-and-fallbacks) | How retries and provider fallbacks work |
| – | [Request flows](#7-request-flows) | Chat streaming, human edits, a full campaign |
| – | [State](#8-state-model) · [Deployment](#9-deployment) · [Quality attributes](#10-quality-attributes) | Memory, runtime topology, cross-cutting concerns |

---

## 1. System context

```mermaid
flowchart LR
    user(["👤 Marketer / content creator<br/>(browser)"])
    dev(["🛠️ Developer / evaluator<br/>(CLI, tests, benchmarks)"])

    subgraph cb ["ContentBlitz"]
        sys["Multi-agent content system<br/>research · SEO blogs · LinkedIn posts · images"]
    end

    subgraph llm ["LLM providers (LangChain chat models)"]
        oai["OpenAI<br/>GPT-4o / GPT-4o-mini"]
        ant["Anthropic<br/>Claude Sonnet / Haiku"]
        gem["Google<br/>Gemini Flash"]
    end
    subgraph search ["Research providers"]
        serp["SERP API<br/>(Google results)"]
        pplx["Perplexity Sonar"]
        tav["Tavily"]
    end
    subgraph img ["Image providers"]
        dalle["OpenAI DALL-E 3 / 2"]
        stab["Stability AI"]
    end
    ls["LangSmith<br/>(optional tracing)"]

    user -- "chat, edit, export (HTTPS)" --> sys
    dev -- "CLI / pytest / make bench" --> sys
    sys -- "prompts → completions,<br/>structured output" --> llm
    sys -- "search queries → results" --> search
    sys -- "image prompts → images" --> img
    sys -. "traces (if enabled)" .-> ls
```

Every external service is optional: with no keys, ContentBlitz runs on built-in offline providers (a LangChain mock
chat model, mock search and a local image renderer), which is also how CI and the demo mode run.

---

## 2. Containers

```mermaid
flowchart TB
    subgraph browser ["Browser"]
        spa["<b>React SPA</b><br/>TypeScript · Vite<br/>Chat · Content · Research · Export · Settings<br/><i>API keys held in tab memory only</i>"]
    end

    subgraph server ["API server process (uvicorn :8000)"]
        api["<b>FastAPI app</b><br/>REST + Server-Sent Events<br/>serves the built SPA"]
        engine["<b>ContentBlitzEngine</b><br/>LangGraph runtime: supervising graph<br/>+ 6 agent subgraphs"]
        svc["<b>Services</b><br/>LLMGateway (LangChain) · search & image ProviderChains<br/>TTL cache · usage tracker"]
        api --> engine --> svc
    end

    subgraph storage ["Local storage (/data volume in Docker)"]
        mem[("Conversation memory<br/>LangGraph checkpointer<br/>in-memory or SQLite file")]
        files[("Generated images<br/>PNG + JSON metadata")]
    end

    cli["<b>CLI</b> (src/cli.py)<br/>terminal chat"]
    bench["<b>Benchmark</b> (scripts/benchmark.py)<br/>latency · cost · quality reports"]
    ext["External providers<br/>(LLMs · search · images · LangSmith)"]

    spa -- "JSON over HTTPS<br/>chat = text/event-stream" --> api
    cli --> engine
    bench --> engine
    engine -- "checkpoint per thread_id" --> mem
    svc -- "save / read" --> files
    api -- "GET /api/images/{file}" --> files
    svc -- "HTTPS" --> ext
```

| Container | Technology | Responsibility |
|---|---|---|
| React SPA | React 18, TypeScript, Vite | Conversational UI with a live six-station agent pipeline, side-by-side editors with re-scoring, research panel with citations, fact-check badges and credibility ratings, exports, settings (offline mode, keys, provider priority, brand voice, usage) |
| FastAPI app | FastAPI, uvicorn, Pydantic | 12 endpoints (see [API docs](api_documentation.md)); streams per-agent progress over SSE; picks an engine per provider configuration via the `EngineRegistry`; strips server paths; serves the SPA |
| ContentBlitzEngine | LangGraph | Runs one conversational turn through the supervising graph; reads/writes checkpointed state |
| Services | LangChain, requests | Model calls with retries + fallbacks; search and image provider chains; caching; usage/cost accounting |
| Conversation memory | LangGraph `MemorySaver` / `SqliteSaver` | Per-thread state across turns (and restarts with SQLite) |
| CLI / benchmark | Python | Terminal chat; scenario benchmarks that write `docs/benchmarks/*.md` |

---

## 3. Backend components

```mermaid
flowchart TB
    api["<b>src/api</b> · HTTP layer<br/>server.py: 12 routes, SSE streaming, EngineRegistry<br/>schemas.py: request models"]
    core["<b>src/core</b> · application<br/>workflow.py: ContentBlitzEngine · router.py: heuristic + IntelligentRouter<br/>config.py: layered settings, tracing · resilience.py: retry, TTLCache, UsageTracker"]
    orch["<b>src/workflow</b> · orchestration<br/>langgraph_workflow.py: supervising StateGraph, next_step, finalize, error isolation<br/>state_management.py: ContentState"]
    agents["<b>src/agents</b> · six LangGraph subgraphs<br/>query_handler · research_agent · content_strategist · blog_writer · linkedin_writer · image_generator<br/>base.py: BaseAgent (build_graph, ask) · prompts.py: ChatPromptTemplates · schemas.py: Pydantic outputs"]
    integ["<b>src/integrations</b> · external services<br/>llm_gateway.py: LangChain chat models, retries, fallbacks, MockChatModel<br/>base.py: ProviderChain · serp / perplexity / tavily / DALL-E / stability / placeholder / mock search<br/>service_factory.py: Services bundle"]
    utils["<b>src/utils</b> · domain logic<br/>content_optimization: SEO, LinkedIn format · quality_validation: scores, brand voice<br/>source_verification: credibility, fact-check · export_tools · templates"]
    ext(["External providers"])

    api --> core --> orch --> agents
    agents --> integ --> ext
    agents --> utils
    api -- "re-score edits, exports" --> utils
    core -- "router uses the gateway;<br/>engine builds Services" --> integ
```

**Dependency rules:** API → core → workflow → agents → integrations/utils; arrows are package dependencies and
nothing depends upward. Agents never import a vendor SDK; they get
a `Services` bundle (`llm` = `LLMGateway`, `research`/`image` = `ProviderChain`s, cache, tracker), so every agent runs
unchanged offline and in tests.

---

## 4. Supervising graph

The engine's top-level LangGraph `StateGraph`. The Query Handler writes a **plan** (an ordered subset of agents); after
every node, the single routing function `next_step` sends control to the next unfinished agent or to `finalize`.

```mermaid
stateDiagram-v2
    [*] --> query_handler
    query_handler --> research: plan has research
    query_handler --> blog: research reused
    query_handler --> linkedin
    query_handler --> image
    query_handler --> finalize: clarification needed
    research --> strategist
    research --> blog
    research --> linkedin
    research --> finalize
    strategist --> blog
    strategist --> finalize
    blog --> linkedin
    blog --> image
    blog --> finalize
    linkedin --> image
    linkedin --> finalize
    image --> finalize
    finalize --> [*]

    note right of query_handler
        next_step(state):
          clarify → finalize
          first agent in plan not yet completed
          otherwise → finalize
    end note
```

- **Canonical order** `research → strategist → blog → linkedin → image` guarantees each agent sees upstream context.
- **Error isolation:** each agent node is wrapped; a failure is recorded in `errors`, dependants are skipped
  (strategist after failed research), and the remaining agents still run. `finalize` composes the reply.
- **Examples:** "Research X" → `[research, strategist]`; "Now a blog about it" → `[blog]` (research reused);
  "Make it shorter" → `[blog]` in refine mode; "Create a campaign about X" → all five.

---

## 5. Agent subgraphs

Each agent is a compiled `StateGraph` with private state, invoked from its node in the supervising graph. LLM steps
are `ChatPromptTemplate | chat model` chains from the gateway; shapes in **bold** produce structured (Pydantic) output.

### Query Handler
```mermaid
flowchart LR
    s((START)) --> route["route<br/><b>RouteDecision</b> (fast tier)<br/>validated · heuristic fallback"] --> plan["plan<br/>reuse same-topic research<br/>clarify if no plan/topic"] --> e((END))
```

### Deep Research
```mermaid
flowchart LR
    s((START)) --> plan["plan<br/>3 sub-queries"]
    plan -- "cache hit" --> e((END))
    plan -- "Send (parallel)" --> s1["search: topic"] & s2["search: statistics"] & s3["search: trends"]
    s1 & s2 & s3 --> merge["merge<br/>dedupe ≤10 sources"] --> analyze["analyze<br/><b>ResearchAnalysis</b><br/>extractive fallback"] --> verify["verify<br/>credibility + fact-check"] --> score["score<br/>quality + cache"] --> e2((END))
```

### Content Strategist
```mermaid
flowchart LR
    s((START)) --> report["report<br/>template · Sources"] & brief["brief<br/><b>ContentBrief</b> (fast)"]
    report & brief --> e((END))
```

### SEO Blog Writer
```mermaid
flowchart LR
    s((START)) -- write --> kw["keywords<br/><b>KeywordPlan</b>"] --> draft["draft<br/>premium tier"] --> meta["meta<br/>150-160 chars"] --> ev{"evaluate<br/>SEO + quality<br/>keep best"}
    s -- "refine (user feedback)" --> edit["edit"] --> ev
    ev -- "score < threshold<br/>and loops left" --> imp["improve<br/>editor prompt"] --> ev
    ev -- "good enough" --> e((END))
```
Series ("3-part blog series") run this subgraph once per part in parallel via `graph.batch`.

### LinkedIn Writer
```mermaid
flowchart LR
    s((START)) -- write --> d["draft"] & h["hashtags<br/><b>HashtagSet</b>"]
    d & h --> lc{"length_check<br/>1,300-1,600 chars"}
    lc -- "out of range,<br/>1 fix left" --> adj["adjust<br/>expand / condense"] --> lc
    lc -- ok --> fin["finalize<br/>format + score"] --> e((END))
    s -- refine --> edit["edit<br/>keep hashtags"] --> fin
```

### Image Generator
```mermaid
flowchart LR
    s((START)) --> enh["enhance<br/>art-director prompt (fast)"] --> gen["generate<br/>DALL-E 3 → DALL-E 2 → Stability → placeholder"] --> st{"store<br/>download · validate · save"}
    st -- valid --> e((END))
    st -- "download/decode failed" --> ph["placeholder<br/>render locally"] --> e
```

---

## 6. LLM call path: retries and fallbacks

```mermaid
flowchart LR
    node["agent node<br/>BaseAgent.ask()"] --> chain["ChatPromptTemplate<br/>| gateway.runnable(tier, schema)"] --> o

    subgraph fb ["with_fallbacks (order from config/services.yaml)"]
        direction LR
        o["ChatOpenAI<br/>.with_retry(transient)"] -- "still failing, or<br/>auth / 4xx / schema error" --> a["ChatAnthropic<br/>.with_retry(transient)"]
        a -- fails --> g["ChatGoogleGenerativeAI<br/>.with_retry(transient)"]
        g -- fails --> m["MockChatModel<br/>offline, always answers"]
    end

    fb -. "callback per attempt:<br/>provider · model · latency · tokens · cost" .-> t[("UsageTracker<br/>Settings panel · /api/usage")]
    fb -. "if LANGSMITH_TRACING" .-> ls["LangSmith"]
```

- **Retried on the same provider:** rate limit, timeout, connection and 5xx errors (exponential backoff with jitter,
  `max_retries` per environment). SDK-internal retries are disabled so this is the only policy.
- **Fail over immediately:** authentication, bad request, and structured output that fails schema validation.
- **Order** comes from `config/services.yaml`; providers without keys are skipped; the user can change the primary
  model in Settings. Search and image calls use the same idea through `ProviderChain`
  (SERP API → Perplexity → Tavily → mock; DALL-E 3 → DALL-E 2 → Stability → placeholder).

---

## 7. Request flows

### 7.1 Chat turn with live progress (SSE)

```mermaid
sequenceDiagram
    autonumber
    participant B as Browser (React)
    participant A as FastAPI
    participant R as EngineRegistry
    participant G as Supervising graph
    participant S as Agent subgraphs
    participant M as Checkpointer
    B->>A: POST /api/threads/{id}/chat {message, settings}
    A->>R: engine for these settings (hashed, LRU, shared checkpointer)
    A-->>B: event: start {providers, offline}
    A->>G: stream(message, thread_id)
    G->>M: load thread state
    loop each planned agent
        G->>S: invoke subgraph
        S-->>G: partial state update
        A-->>B: event: node {node, trace, plan?}
    end
    G->>M: save state (messages, artefacts, history)
    A-->>B: event: done {UI-safe state}
```

### 7.2 Human edit and re-score

```mermaid
sequenceDiagram
    participant B as Browser
    participant A as FastAPI
    participant Q as quality_validation
    participant M as Checkpointer
    B->>A: PUT /api/threads/{id}/artifacts/blog {markdown, meta}
    A->>M: read state (brand voice, keywords)
    A->>Q: score_blog + analyze_seo
    A->>M: update_state(blog, as_node="finalize")
    A-->>B: re-scored blog (revision +1)
```

### 7.3 Research-first campaign

```mermaid
sequenceDiagram
    participant U as User
    participant QH as Query Handler
    participant R as Research
    participant S as Strategist
    participant B as Blog
    participant L as LinkedIn
    participant I as Image
    U->>QH: "Create a campaign about urban beekeeping"
    QH->>QH: route: structured RouteDecision (fast tier) → validate → plan
    QH->>R: plan=[research,strategist,blog,linkedin,image]
    R->>R: Send ×3: sub-queries searched in parallel (cached) → merge, dedupe ≤10 sources
    R->>R: analyze (structured ResearchAnalysis, [n] citations) → verify (credibility + fact-check) → score
    R->>S: research
    par strategist branches
        S->>S: report (template + Sources)
    and
        S->>S: brief (structured ContentBrief)
    end
    S->>B: brief
    B->>B: keywords → draft (premium) → meta (fast) → evaluate ⇄ improve while score < threshold
    B->>L: blog title + brief + stats
    L->>L: draft ‖ hashtags (8-12) → length_check ⇄ adjust → finalize (format + score)
    L->>I: topic, platform
    I->>I: enhance prompt → DALL-E 3 → (fallbacks) → store + validate → placeholder if download fails
    I->>U: finalize: summary, scores, suggestions, next-step tip
```

---

## 8. State model

`ContentState` (a `TypedDict`) is checkpointed per `thread_id`.

| Field | Lifetime | Notes |
|---|---|---|
| `messages` | conversation | `operator.add` reducer; user message added on input, assistant message on finalize |
| `user_query`, `route`, `plan`, `completed`, `errors`, `trace`, `topic`, `tone`, `templates`, `series_count`, `refine_target`, `feedback`, `needs_clarification`, `response` | turn | reset by the Query Handler |
| `research` (with `verification` and per-source `credibility`), `strategy_report`, `content_brief`, `blog`, `blog_series`, `linkedin`, `image` | conversation | artefacts, each tagged with its `topic` so stale artefacts are never reused for a new topic |
| `history` | conversation | `last_topic`, `last_agents`, `turn`, used for context-aware routing |
| `brand_voice` | conversation | per-thread override set from the UI (manual or learned) |

Memory is `MemorySaver` by default or `SqliteSaver` with `CONTENTBLITZ_MEMORY=sqlite` (the Docker default). The browser
stores its `thread_id` and restores the conversation on reload. Content-tab edits are written back with
`graph.update_state(..., as_node="finalize")`. See [ADR-0005](adr/0005-conversation-memory.md).

---

## 9. Deployment

```mermaid
flowchart TB
    subgraph ci ["GitHub Actions (every push / PR)"]
        fe["frontend job<br/>tsc · Vitest · vite build"] --> be["backend job · Python 3.11 + 3.12<br/>ruff · pytest + Playwright e2e · coverage ≥ 80%"] --> dk["docker job<br/>build image · smoke-test /api/health + SPA"]
    end

    subgraph build ["Multi-stage Dockerfile"]
        n["node:22-alpine<br/>npm ci · npm run build"] -- "frontend/dist" --> p["python:3.12-slim<br/>pip install · src/ config/ scripts/"]
    end

    subgraph host ["Host (Docker Compose / Railway / Render / Fly.io)"]
        subgraph c ["container: contentblitz (non-root)"]
            uv["uvicorn src.api.server:app :8000<br/>SPA + REST + SSE<br/>HEALTHCHECK /api/health"]
        end
        vol[("/data volume<br/>outputs/images · contentblitz_memory.sqlite")]
        env["env: API keys · APP_ENV=production<br/>CONTENTBLITZ_MEMORY=sqlite · LANGSMITH_*"]
        uv --- vol
        env -.-> uv
    end

    user(["Browser"]) -- "HTTPS (TLS at the proxy)" --> rp["reverse proxy<br/>no buffering on /api/threads/*/chat"] --> uv
    uv -- HTTPS --> prov["LLM · search · image providers · LangSmith"]
    dk -.-> p
```

- **Single instance (default):** one container, SQLite memory and images on the `/data` volume.
- **Scaling out:** run several replicas behind the proxy, pass a shared LangGraph `PostgresSaver` as the registry's
  checkpointer, and move the TTL cache to Redis; generated images go to shared/object storage.
- **Development:** `make api` (FastAPI :8000) + `make web` (Vite :5173 proxying `/api`), or `make demo` offline.

---

## 10. Quality attributes

| Attribute | How the architecture provides it |
|---|---|
| Availability / resilience | Retries on transient errors, provider fallbacks for LLMs, search and images, offline providers last; per-agent error isolation; degradations inside subgraphs (heuristic routing, extractive research, placeholder image) |
| Performance | Parallel research searches, strategist branches, LinkedIn draft ‖ hashtags, parallel series parts; 30-minute search/research cache; research reused across turns; fast model tier for small tasks |
| Cost | Model tiers, caching, research reuse, capped auto-rewrites; per-call cost tracking; `make bench` reports |
| Content reliability | Research-first writing, `[n]` citations, source credibility ratings and claim verification, quality scores with auto-rewrite |
| Observability | Live pipeline in the UI, per-attempt usage tracker, structured logs, optional LangSmith traces of every node and model call |
| Security | Browser-held API keys sent per request, never stored or logged (engine selected by hashed config); no server paths in responses; image path-traversal checks; non-root container; CORS limited to dev origins |
| Testability | Every external dependency behind an interface with an offline implementation; 155 Python tests incl. subgraph structure and the real `ChatOpenAI` client against a local server; Playwright browser tests |
| Modifiability | Prompts in one module, Pydantic schemas for outputs, providers configured in YAML, new agents = new subgraph + plan entry |

## 11. Decision records

| ADR | Decision |
|---|---|
| [0001](adr/0001-agents-as-langgraph-subgraphs-with-langchain-models.md) | Agents as LangGraph subgraphs calling LangChain chat models |
| [0002](adr/0002-react-fastapi-sse-ui.md) | React SPA + FastAPI with Server-Sent Events instead of Streamlit |
| [0003](adr/0003-provider-retry-and-fallback-strategy.md) | Retry transient errors per provider, then fall back across providers, offline last |
| [0004](adr/0004-deterministic-fact-checking.md) | Deterministic source credibility and claim verification |
| [0005](adr/0005-conversation-memory.md) | Conversation memory with LangGraph checkpointers |
