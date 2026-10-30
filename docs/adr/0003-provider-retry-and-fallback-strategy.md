# ADR-0003: Retry transient errors per provider, then fall back across providers, offline last

**Status:** Accepted
**Date:** 2026-10-29
**Deciders:** Prasanna Koppolu (project owner)

## Context
The brief requires "comprehensive error handling and fallback mechanisms for API failures", multiple providers
(OpenAI, Claude, Gemini; SERP API, Perplexity; DALL-E, alternatives) and targets 99.9% availability. Provider errors
differ in kind: rate limits and 5xx errors are usually transient; bad keys and malformed requests are not. Evaluators
and CI must be able to run without any keys.

## Decision
- **LLMs:** each LangChain chat model is wrapped with `with_retry` for transient errors only (rate limit, timeout,
  connection, 5xx; exponential backoff with jitter; `max_retries` per environment, SDK retries disabled), and the models
  are chained with `with_fallbacks` in the configured order. Auth/4xx errors and schema-invalid structured output
  move to the next provider immediately.
- **Search and images:** the same policy in `ProviderChain` over HTTP adapters.
- **Offline providers last** in every chain (LangChain `MockChatModel`, mock search, local placeholder renderer).
- Every attempt is recorded (provider, model, latency, tokens, cost) and shown in the UI and LangSmith.

## Options Considered

### Option A: Single provider with retries
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Cost | Lowest |
| Scalability | Availability bounded by one vendor |
| Team familiarity | High |

**Pros:** simple. **Cons:** one outage or bad key takes the product down; fails the brief's fallback requirement.

### Option B: Retry everything, then fall back
**Pros:** simple rule. **Cons:** retrying a 401 wastes time and quota; slower failover.

### Option C: Classified retry + ordered fallback + offline last (chosen)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium |
| Cost | Retries only where they can succeed; mock costs nothing |
| Scalability | Availability = 1 − Π(provider failure); offline floor |
| Team familiarity | Medium (LangChain primitives) |

**Pros:** fast failover on permanent errors; resilience to vendor outages; always returns something; fully testable
offline. **Cons:** a degraded answer may come from the mock during a full outage (labelled in the UI); more paths to test.

### Option D: Load-balance across providers concurrently
**Pros:** lower tail latency. **Cons:** multiplies cost; inconsistent voice between providers; unnecessary here.

## Trade-off Analysis
Classification is what makes C both fast and cheap: transient errors get retried where a retry can succeed, permanent
ones fail over immediately. Putting the offline provider last trades answer quality during a total outage for
availability and testability, made visible to the user.

## Consequences
- Easier: running anywhere without keys; switching provider order in YAML or Settings; diagnosing failures from the
  attempt log or LangSmith.
- Harder: keeping the transient-error list current as SDKs change (`transient_errors()` in `llm_gateway.py`).
- Revisit: Gemini's 429 surfaces as a generic client error and is treated as permanent (fails over instead of retrying).

## Action Items
1. [x] `LLMGateway` with classified `with_retry` and `with_fallbacks` (PR #4)
2. [x] Tests: transient retried, auth not retried, schema-invalid output falls back, real `ChatOpenAI` 429/401 against a local server
3. [ ] Add a circuit breaker so a provider that keeps failing is skipped for a cool-down period
