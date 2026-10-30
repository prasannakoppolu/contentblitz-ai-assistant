# API Documentation

## HTTP API (`src/api/server.py`)

Interactive OpenAPI docs: `http://localhost:8000/docs`. Conversation memory backend: `CONTENTBLITZ_MEMORY` (`memory` | `sqlite`).

| Method & path | Body | Response |
|---|---|---|
| `GET /api/health` | – | `{status, time}` |
| `GET /api/config` | – | detected key names, default demo mode, quality threshold, fallback chains, default brand voice |
| `POST /api/threads` | – | `{thread_id}` |
| `GET /api/threads/{tid}/state` | – | UI-safe state (messages, research, blog, linkedin, image with `src`, trace, …) |
| `POST /api/threads/{tid}/chat` | `{message, settings}` | `text/event-stream` (below) |
| `PUT /api/threads/{tid}/artifacts/blog` | `{markdown, meta_description}` | re-scored blog (revision +1) |
| `PUT /api/threads/{tid}/artifacts/linkedin` | `{text}` | re-scored post |
| `PUT /api/threads/{tid}/brand-voice` | `BrandVoice` | saved voice |
| `POST /api/brand-voice/learn` | `{samples[], base?}` | learned `BrandVoice` (not saved) |
| `POST /api/usage` | `settings` | calls, failures, tokens, cost, cache, provider chains, `offline` |
| `GET /api/threads/{tid}/export/{artifact}/{fmt}` | – | download; `blog`/`report`: `md html txt pdf wxr`; `series`: `wxr`; `linkedin`: `txt json` |
| `GET /api/images/{file}` | – | generated image |

`settings` (`ClientSettings`): `{demo_mode?, api_keys{openai,anthropic,gemini,serpapi,perplexity,tavily,stability},
llm_primary?, research_primary?, quality_threshold?}`. Omitted fields fall back to server config.

**Chat stream events**

```
event: start  data: {"thread_id": "...", "providers": {"llm": [...], ...}, "offline": true}
event: node   data: {"node": "query_handler", "trace": {...}, "plan": ["research","blog"], "topic": "..."}
event: node   data: {"node": "research", "trace": {"agent":"research","status":"ok","detail":"10 sources via serpapi", ...}}
...
event: done   data: { full UI-safe state }
event: error  data: {"message": "..."}        # stream ends after an error
```

## Engine (`src/core/workflow.py`)

```python
engine = ContentBlitzEngine(settings: Settings | None = None, services: Services | None = None,
                            checkpointer=None, memory: str = "memory")   # memory: "memory" | "sqlite"
```

| Method | Returns | Description |
|---|---|---|
| `run(query, thread_id="default")` | `dict` (full state) | Executes one conversational turn |
| `stream(query, thread_id)` | iterator of `(node, update)` | Live progress, one item per agent |
| `get_state(thread_id)` | `dict` | Current checkpointed state |
| `update_artifact(thread_id, key, value)` | `None` | Persist human edits (e.g. `"blog"`, `"linkedin"`) |
| `set_brand_voice(thread_id, BrandVoiceConfig)` | `None` | Per-conversation brand voice |
| `usage()` | `dict` | Calls, failures, tokens, est. cost, cache stats, active provider chains |
| `new_thread_id()` | `str` | Static helper |

## Agents

Each agent is a **LangGraph subgraph** (`agent.graph`, a `CompiledStateGraph`) mounted as a node of the main
workflow, and calls models through LangChain chains: `ChatPromptTemplate` (all prompts live in
`src/agents/prompts.py`) piped into the gateway's chat model, with Pydantic schemas from `src/agents/schemas.py`
for structured output.

```python
class BaseAgent:
    graph: CompiledStateGraph                       # built by build_graph()
    def run(state: dict) -> dict                    # map workflow state -> subgraph -> partial update
    def ask(prompt, inputs, *, task, context=None, tier="standard", temperature=0.7,
            max_tokens=2500, schema=None) -> LLMResult_   # prompt | model (retries + fallbacks)
```

Agents also expose `research_for/brief_for/blog_for(state)` helpers that only return artefacts matching the
current topic.

| Agent | Subgraph |
|---|---|
| Query Handler | `route` (structured `RouteDecision`, heuristic fallback) → `plan` |
| Deep Research | `plan` → `Send` fan-out → `search` ×3 **in parallel** → `merge` → `analyze` (`ResearchAnalysis`) → `verify` → `score`; cache hit short-circuits to END |
| Content Strategist | `report` ‖ `brief` (`ContentBrief`), parallel branches |
| SEO Blog Writer | write: `keywords` (`KeywordPlan`) → `draft` → `meta` → `evaluate`; refine: `edit` → `evaluate`; `evaluate` ⇄ `improve` loop while score < threshold |
| LinkedIn Writer | write: `draft` ‖ `hashtags` (`HashtagSet`) → `length_check` ⇄ `adjust` → `finalize`; refine: `edit` → `finalize` |
| Image Generator | `enhance` → `generate` (provider chain) → `store` → (`placeholder` if download/validation fails) |

### 1. Query Handler (`QueryHandlerAgent`)

**Reads:** `user_query`, `history`, `research`, `messages`
**Writes:** `route`, `plan`, `topic`, `tone`, `templates`, `series_count`, `refine_target`, `feedback`,
`needs_clarification`, `response` (help text when clarifying); resets `completed`, `errors`, `trace`.

`route` schema:

```json
{"intents": ["blog"], "plan": ["research", "blog"], "topic": "remote onboarding", "tone": "casual",
 "templates": {"blog": "how_to"}, "series_count": 0, "refine_target": null,
 "needs_clarification": false, "confidence": 0.9, "reasoning": "...", "router": "llm|heuristic|heuristic-fallback"}
```

### 2. Deep Research (`DeepResearchAgent`)

**Reads:** `topic` · **Writes:** `research`

```json
{"topic": "...", "summary": "...", "key_findings": ["... [1]"], "statistics": ["62% ... [2]"],
 "trends": [], "audience_insights": [], "content_angles": [], "keywords": [],
 "sources": [{"title": "", "url": "", "snippet": "", "published": null}],
 "search_providers": ["serpapi"], "analysis_provider": "openai", "queries": ["..."],
 "verification": {...}, "quality": {"score": 0, "grade": "A", "dimensions": {"source_coverage": 0, "source_diversity": 0,
             "depth": 0, "attribution": 0, "source_credibility": 0, "fact_check": 0}},
 "offline_demo": false, "created_at": 0}
```

Process: 3 sub-queries (`topic`, `topic statistics <year>`, `topic trends and challenges`) searched **in parallel**
(cached 30 min) → URL de-duplication (≤10) → structured LLM analysis with `[n]` citations → **fact-check**
(source credibility + claim verification, `src/utils/source_verification.py`) → research quality score.
Fallback: extractive summary from snippets if every LLM fails; raises only if *no* search succeeds.

Fact-check output (`research.verification`; each source also carries `credibility`):

```json
{"claims": [{"claim": "62% of teams ... [1]", "kind": "statistic", "citations": [1],
             "status": "supported|weak|unverified|uncited|invalid_citation", "note": "..."}],
 "summary": {"avg_source_credibility": 78, "high_credibility_sources": 4, "low_credibility_sources": 1,
             "claims_checked": 9, "supported": 6, "needs_review": 3, "verification_rate": 0.67}}
```

Source credibility: `{"domain": "hbr.org", "score": 88, "tier": "high|medium|low", "reasons": ["recognised research or news publisher"]}`.

### 3. Content Strategist (`ContentStrategistAgent`)

**Reads:** `research`, `templates.research`, `tone`, brand voice · **Writes:** `strategy_report` (Markdown with Sources),
`content_brief` `{primary_keyword, secondary_keywords, audience, angle, key_messages, template, topic}`.
Report templates: `trend_report`, `market_analysis`, `competitive_analysis`.

### 4. SEO Blog Writer (`SEOBlogWriterAgent`)

**Reads:** `topic`, `research`, `content_brief`, `templates.blog`, `tone`, `series_count`, `refine_target`, `feedback`
**Writes:** `blog`, `blog_series`

```json
{"title": "", "slug": "", "topic": "", "markdown": "", "meta_description": "(150-160 chars)",
 "primary_keyword": "", "secondary_keywords": [], "template": "how_to|listicle|comparison|thought_leadership",
 "word_count": 0, "seo": {"keyword_density": 1.4, "h1_count": 1, "h2_count": 5, "internal_link_suggestions": [], "issues": [], "score": 0},
 "quality": {"score": 0, "grade": "", "dimensions": {"seo": 0, "readability": 0, "structure": 0, "brand_voice": 0, "evidence": 0}, "suggestions": []},
 "sources": [], "provider": "openai", "revision": 1, "refinement_loops": 0}
```

### 5. LinkedIn Writer (`LinkedInWriterAgent`)

**Reads:** `topic`, `research`, `blog`, `content_brief`, `templates.linkedin`, `tone`, `refine_target`, `feedback`
**Writes:** `linkedin` `{text, body, hashtags[8-12], template, char_count, hook, quality, provider, revision, topic}`.
Templates: `industry_insight`, `personal_story`, `tips`, `announcement`.

### 6. Image Generator (`ImageGenerationAgent`)

**Reads:** `topic`, `user_query`, `plan`, `blog` · **Writes:** `image`

```json
{"provider": "dalle3", "model": "dall-e-3", "url": "...", "path": "outputs/images/<slug>-<ts>.png",
 "width": 1792, "height": 1024, "format": "PNG", "enhanced_prompt": "...", "revised_prompt": "...",
 "platform": "blog|linkedin|default", "alt_text": "...", "attempts": [{"provider": "dalle3", "ok": true}],
 "quality": {...}}
```

Sizes: blog 1792×1024, LinkedIn 1024×1024. Metadata is also written next to the image as `<stem>.json`.

## LLM gateway (`src/integrations/llm_gateway.py`)

```python
gw = services.llm                                   # LLMGateway
model = gw.runnable(tier="standard", temperature=0.7, max_tokens=2000, schema=None)
#   -> ChatOpenAI.with_retry(...)  .with_fallbacks([ChatAnthropic..., ChatGoogleGenerativeAI..., MockChatModel])
#      (with schema: each model's .with_structured_output(schema))
result = gw.invoke(PROMPT | model, {"topic": "..."}, task="blog", context={...})
result.output / result.text / result.provider / result.attempts
gw.names            # e.g. ["openai", "anthropic", "mock"]
```

* Retries: `with_retry` on transient errors only (rate limit, timeout, connection, 5xx); `max_retries` from config.
  SDK-internal retries are disabled so this is the single policy. Auth / bad-request errors fail over immediately.
* Fallbacks: order from `config/services.yaml` → `fallback_chains.llm`; providers without keys are skipped; the
  offline `MockChatModel` (a real `BaseChatModel`) is always last.
* `models.<provider>.base_url` points `ChatOpenAI` at any OpenAI-compatible endpoint (Azure OpenAI, vLLM, Ollama…).
* Every attempt is recorded (provider, model, latency, tokens, cost) via a LangChain callback; LangSmith traces
  every chain and graph node when `LANGSMITH_TRACING=true`.

## Research and image providers (`src/integrations/base.py`)

```python
class SearchProvider: search(query, num_results=8) -> SearchResponse(query, sources, provider, answer, related_queries)
class ImageProvider:  generate_image(prompt, size="1024x1024", style="vivid") -> ImageResponse
ProviderChain(kind, providers, tracker).search / .generate_image   # failover + per-thread .attempts
```

To add a search or image provider: implement the interface (use `HTTPProviderMixin._request` for retry
semantics), register it in `service_factory.py`, add its key to `API_KEY_ENV`, and list it in
`config/services.yaml` → `fallback_chains`. To add an LLM provider, add a branch in `build_chat_model`.

## Utilities

| Function | Module | Purpose |
|---|---|---|
| `analyze_seo(md, keyword, meta, secondary)` | `content_optimization` | Full SEO audit → `SEOReport` |
| `readability(text)` | `content_optimization` | Flesch reading ease, FK grade |
| `fit_meta_description(text, kw)` | `content_optimization` | Clamp into 150-160 chars keeping keyword |
| `format_linkedin_post(body, tags)` / `analyze_linkedin(post)` | `content_optimization` | Format & audit |
| `score_blog / score_linkedin / score_research / score_image` | `quality_validation` | `QualityReport` |
| `brand_voice_check(text, voice)` / `learn_brand_voice(samples)` | `quality_validation` | Voice consistency / learning |
| `export_content(md, fmt)` | `export_tools` | `md`, `html`, `txt`, `pdf`, `wxr` |
| `credibility(source)` / `verify_claims(claims, sources)` / `verify_research(report)` | `source_verification` | Source credibility and citation fact-check |
| `to_wordpress_wxr(posts)` / `to_social_json(...)` | `export_tools` | CMS / scheduler payloads |
