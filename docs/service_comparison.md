# Service Comparison Analysis

> Pricing is indicative public list pricing as of late 2026 and changes often; check provider pricing pages
> before budgeting. §5 gives an evaluation protocol and a results table to fill in. Run it with your keys
> (`python -m src.cli "<prompt>"` with different `fallback_chains`) to produce numbers for your own workload.

## 1. LLMs

| Provider / model | Input / output per 1M tokens | Strengths | Weaknesses | Role in ContentBlitz |
|---|---|---|---|---|
| OpenAI GPT-4o | ~$2.50 / $10 | Reliable JSON mode, strong marketing copy, fast | Can sound generic without voice constraints | Primary (standard/premium) |
| OpenAI GPT-4o-mini | ~$0.15 / $0.60 | Very cheap, good at classification/short copy | Weaker long-form | Fast tier: routing, meta, hashtags, prompts |
| Anthropic Claude Sonnet | ~$3 / $15 | Best long-form reasoning and natural voice, follows style rules closely | Higher output cost | Fallback #1; consider as primary for thought leadership |
| Anthropic Claude Haiku | ~$1 / $5 | Fast, solid instruction following | Less depth | Fast tier when Claude is primary |
| Google Gemini 2.0 Flash | ~$0.10 / $0.40 (free tier available) | Cheapest, generous free tier, native JSON mime type | Less consistent tone | Fallback #2; best for development |

## 2. Research engines

| Provider | Pricing model | Strengths | Weaknesses | Role |
|---|---|---|---|---|
| SERP API (Google) + LLM | Per-search plans (free tier ~100/mo) | Full control of sources, real Google rankings, numbered citations we control | Two-step (search + analyse) → extra LLM tokens | Primary |
| Perplexity Sonar Pro | Per-request + tokens | Research + analysis in one call, recent web, citations returned | Less control over source selection, citations as bare URLs | Fallback #1 / simpler alternative |
| Tavily | Credit-based (free tier ~1k/mo) | Built for agents, clean extracted content, `include_answer` | Smaller index than Google | Fallback #2 |
| You.com Search API | Usage-based | Web + news, LLM-ready snippets | Not integrated (same interface; easy to add) | — |

**SERP API + GPT vs Perplexity Sonar:** SERP+GPT wins on *control and attribution* (we choose sources,
de-duplicate, number them, and require `[n]` citations). Perplexity wins on *simplicity and latency* (1 call vs 4).
ContentBlitz uses SERP first and lets Perplexity's pre-analysed answer enrich the LLM context when it's the active provider.

## 3. Image generation

| Provider | Price per image | Quality for marketing | Notes | Role |
|---|---|---|---|---|
| DALL-E 3 | ~$0.04 (1024²) / $0.08 (1792×1024) | Excellent prompt adherence, returns revised prompt | Occasional text artefacts despite instructions | Primary |
| DALL-E 2 | ~$0.02 | Lower fidelity, very reliable | Max 1024² | Fallback #1 |
| Stability (Stable Image Core) | ~$0.03 | Strong artistic range, aspect ratios | Different prompt style | Fallback #2 |
| Google Imagen | Usage-based | Enterprise / Vertex integration | GCP setup | Optional |
| Midjourney | Subscription | Best aesthetics | No official API (Discord) | Not integrated |
| Local placeholder | $0 | Branded gradient card | Not AI | Last resort |

## 4. Recommended configurations

| Use case / budget | LLM chain | Research chain | Image chain | Est. cost per campaign |
|---|---|---|---|---|
| **Free / student dev** | Gemini Flash → mock | Tavily (free) → mock | placeholder | ≈ $0 |
| **Lean startup** | GPT-4o-mini (all tiers) → Gemini | SERP API → Tavily | DALL-E 2 | ≈ $0.03-0.05 |
| **Balanced (default)** | GPT-4o → Claude → Gemini | SERP API → Perplexity → Tavily | DALL-E 3 → DALL-E 2 → Stability | ≈ $0.15-0.20 |
| **Premium thought leadership** | Claude Sonnet → GPT-4o | Perplexity Sonar Pro → SERP | DALL-E 3 HD → Stability | ≈ $0.30-0.45 |
| **High availability** | All three LLMs, multiple keys as extra providers | All three engines | All three image APIs | balanced + ~5% retries |

Switch by editing `config/services.yaml` → `fallback_chains`/`models`, or in the app under Settings → **Providers and quality**.

## 5. Evaluation protocol (performance benchmarks)

Run the same 5 prompts (research-only, blog, LinkedIn, image, campaign) per configuration and record:

| Metric | How it's measured in ContentBlitz |
|---|---|
| Latency per agent | `trace[*].duration_s` (shown in chat progress) |
| Cost | `engine.usage()["total_cost_usd"]` |
| Content quality | `blog.quality.score`, `linkedin.quality.score`, `research.quality.score` |
| SEO compliance | `blog.seo.issues` count, keyword density, meta length |
| Reliability | `engine.usage()["failures"]`, `image.attempts` |

Benchmark results table (fill in from your own runs; the project ships without live-provider numbers because
the build and CI run fully offline):

| Configuration | Avg latency / campaign | Cost / campaign | Blog quality | LinkedIn quality | Failures |
|---|---|---|---|---|---|
| Balanced (default) | _tbd_ | _tbd_ | _tbd_ | _tbd_ | _tbd_ |
| Lean (4o-mini + SERP + DALL-E 2) | _tbd_ | _tbd_ | _tbd_ | _tbd_ | _tbd_ |
| Claude-first | _tbd_ | _tbd_ | _tbd_ | _tbd_ | _tbd_ |
| Free (Gemini + Tavily) | _tbd_ | _tbd_ | _tbd_ | _tbd_ | _tbd_ |
| Offline mock (measured) | < 1 s | $0 | 85-95 | 95-100 | 0 |

Expected characteristics based on provider documentation and common practice (verify with the table above):

- **Routing:** the heuristic router alone resolves the phrasing variants covered in `tests/unit/test_router.py`; the LLM
  router is there for unusual phrasing ("spin up some socials for our launch").
- **Writing:** Claude Sonnet is generally regarded as strongest for natural long-form voice; GPT-4o for speed and strict
  JSON; Gemini Flash for low-cost drafts.
- **Research:** SERP + LLM gives the tightest citation control; Perplexity needs one call instead of four, so it should
  be noticeably faster for research-only turns.
- **Images:** DALL-E 3 is known for prompt adherence on blog heroes; Stability for stylised/illustrative looks.

## 6. Open source vs proprietary

| Aspect | Proprietary APIs (default) | Open source (e.g. Llama via Ollama/Together, SDXL via Replicate) |
|---|---|---|
| Quality | Highest out of the box | Competitive with tuning |
| Cost at scale | Linear per call | Fixed infra; cheaper at high volume |
| Data control | Vendor terms | Full control / self-host |
| Ops effort | None | GPU hosting, upgrades |

Adding an OpenAI-compatible open-source endpoint is a ~20-line `LLMProvider` (reuse `OpenAIChatProvider` with a custom `base_url`).
