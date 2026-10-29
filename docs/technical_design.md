# Technical Design Document

## 1. Goals & constraints

- Six specialised agents with clear separation of concerns and intelligent routing.
- Production-grade resilience: no single vendor outage should break the product.
- Evaluator-friendly: runs offline, deterministic tests, one-command start.
- Cost-aware: cache, model tiers, artefact reuse.

## 2. Key decisions & trade-offs

| # | Decision | Trade-off |
|---|---|---|
| D1 | **Single dynamic graph** (plan + `next_step`) instead of one graph per workflow | Less visual specificity per workflow, but any agent subset/order works with no new wiring, including refinements and future agents |
| D2 | **LLM router + heuristic fallback + validation** | Extra small call per turn (~$0.0002 on 4o-mini) buys robust follow-up resolution; heuristic guarantees routing works during outages and in tests |
| D3 | **Research-first enforced in validation** | Slightly higher cost for written content, but every blog/post is grounded in cited sources (credibility, E-E-A-T) |
| D4 | **Raw HTTP adapters, not vendor SDKs** | We maintain request shapes, but get uniform retry/error classification (429/5xx retry, 401/403 fail-fast) across 9 providers and a small dependency footprint |
| D5 | **Mock providers as last link of every chain** | Content during a total outage is templated rather than AI-written, which is clearly labelled in the UI; in exchange the product stays usable, and tests/CI/demos need no keys |
| D6 | **Artefacts tagged with topic** | Prevents stale research/brief reuse when the user switches topics mid-conversation |
| D7 | **Deterministic quality scoring** (rules + metrics), not LLM-as-judge | Cheap, explainable, testable; LLM judge could be added as an extra dimension |
| D8 | **Error isolation per node** | A failed image doesn't lose the blog; dependants are skipped explicitly rather than running on missing inputs |
| D9 | **Checkpointer memory** (MemorySaver, or SqliteSaver via `CONTENTBLITZ_MEMORY=sqlite`) | Simple, no infra. Multi-instance deployments should switch to `PostgresSaver` |
| D10 | **React SPA + FastAPI with SSE** (replacing Streamlit) | Two codebases (TS + Python) instead of one, but real-time agent progress, side-by-side editing, responsive layout and conventional deployment; the API is also reusable by other clients |
| D11 | **Keys sent per request, engines cached by hashed config** | Keys travel with each call (HTTPS required in production) but are never stored server-side; LRU cap bounds memory |

## 3. Service integration patterns

```
Agent ──► ProviderChain.generate(...) ──► Provider A ──► HTTPProviderMixin._request (retry/backoff)
                                   └─fail─► Provider B ──► ...
                                   └─fail─► Mock (always succeeds)
```

- **Retry policy:** `retry_with_backoff(max_retries, base_delay)`: delay = base·2^(n-1) + 10% jitter, capped at 20s.
  Configured per environment (`development`: 2 retries / 0.5s; `production`: 4 / 1.5s).
- **Classification:** network / 429 / 5xx → retryable `ProviderError`/`RateLimitError`; 401/403/other 4xx → non-retryable.
- **Observability:** every attempt is recorded (`chain.attempts`, `UsageTracker`) with provider, model, latency, tokens,
  estimated cost; surfaced in the live pipeline, the image "Provider attempts" table and the Settings usage panel (`POST /api/usage`).
- **Model tiers:** `fast` for routing, keywords, meta, hashtags and image prompts; `premium` for long-form.

## 4. Content quality validation & enhancement

| Asset | Dimensions (weight) | Rules |
|---|---|---|
| Blog | SEO (35%), readability (15%), structure (15%), brand voice (20%), evidence (15%) | density 1-2%, meta 150-160, single H1, ≥3 H2, keyword in title/intro/subheading, ≥900 words, Flesch 50-75 ideal, bullets + CTA, stats present |
| LinkedIn | platform fit (35%), hook (20%), engagement (25%), brand voice (20%) | 1,300-1,600 chars, 8-12 hashtags, hook ≤150 chars with number/question, CTA + question, lines ≤220 chars |
| Research | coverage, diversity, depth, attribution (equal) | ≥5 sources, distinct domains, findings + stats, `[n]` citations |
| Image | resolution, prompt quality, provider, format | ≥1024 px, rich prompt, AI provider vs placeholder |

**Enhancement loop:** if a blog scores below `quality_threshold` (70 dev / 75 prod), the writer sends the top
suggestions to an editor prompt and keeps the better version, up to `max_refinement_loops`. LinkedIn posts get a
length-guard pass (expand/condense) before formatting. Human edits saved in the Content tab are re-scored by the API immediately.

**Brand voice:** a `BrandVoiceConfig` (tone, audience, style rules, banned phrases, preferred terms) is injected into
every writer prompt and validated afterwards (banned/generic phrases, tone markers, passive ratio, second-person use).
`learn_brand_voice(samples)` derives tone, sentence length and signature vocabulary from the user's own content.

## 5. Routing details

1. Heuristic baseline: regex intent detection, refine detection, follow-up pronoun resolution, topic extraction
   (strip commands/content nouns/trailing clauses), template, tone and series detection.
2. LLM decision (JSON) with conversation context; validated: unknown agents dropped, research-first enforced,
   canonical ordering applied, missing fields filled from the baseline.
3. Query Handler post-processing: reuse same-topic research, clarification if no plan/topic.

Ambiguous requests with a topic default to a research report; greetings and topic-less requests return help.

## 6. Scalability & performance

- **Stateless engine + external checkpointer:** run multiple API replicas behind a load balancer with
  `PostgresSaver` (LangGraph) for shared memory.
- **Cache:** in-process TTL cache; swap for Redis to share across replicas (same `get/set` interface).
- **Latency:** research sub-queries are independent and can be parallelised with a thread pool; image generation
  can run concurrently with LinkedIn writing via a LangGraph fan-out edge.
- **Throughput limits:** provider rate limits handled by backoff; multiple API keys can be modelled as additional
  providers in a chain.
- **Cost envelope** (GPT-4o + SERP API + DALL-E 3, full campaign): ~6 LLM calls (~12k tokens ≈ $0.06), 3 searches
  (≈ $0.03-0.05 on SERP API paid plans), 1 image ($0.04 standard 1024², $0.08 1792×1024) → roughly **$0.15-0.20 per campaign**.
  Follow-ups that reuse research cost ~$0.02-0.03.

## 7. Security

- Keys come from env/.env on the server, or from the browser: typed into Settings, held in the tab's memory only
  (not localStorage) and sent with each request. The server hashes the provider configuration to select an engine
  and never logs or persists keys. Serve over HTTPS in production.
- The API strips server file paths from responses; images are served by filename with path-traversal checks.
- CORS is limited to the Vite dev origins; production serves UI and API from one origin.
- No user data in URLs except provider-required query params (SERP API key per their API).
- Docker image runs as a non-root user; outputs on a dedicated volume.
