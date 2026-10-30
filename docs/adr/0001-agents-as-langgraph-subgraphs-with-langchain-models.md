# ADR-0001: Agents as LangGraph subgraphs calling LangChain chat models

**Status:** Accepted (supersedes the first implementation, where agents were plain Python functions inside LangGraph nodes calling providers over raw HTTP)
**Date:** 2026-10-29
**Deciders:** Prasanna Koppolu (project owner)

## Context
The capstone brief names **LangGraph** as the multi-agent framework (LangChain components as the natural companion)
and grades "Multi-Agent Architecture" (25%) and "LangGraph Workflow" (10%). The first version used LangGraph only
for top-level orchestration; each agent's internal steps (search → analyse, draft → score → rewrite) were hidden inside
Python methods, and LLM calls went through a hand-written HTTP layer. That worked, but reviewers could not see the
agents' control flow, structured output relied on hand-parsing JSON, and retries/fallbacks/tracing were custom code.

Forces: the brief's framework stack; six agents with real internal workflows (loops, parallel steps); multi-provider
fallbacks must keep working; everything must run offline for CI and evaluators; deterministic tests.

## Decision
Keep the LangGraph supervising graph, and implement **each agent as its own LangGraph subgraph** (compiled
`StateGraph` with private state) mounted as a node. All model calls are **LangChain chains**:
`ChatPromptTemplate | ChatOpenAI / ChatAnthropic / ChatGoogleGenerativeAI`, with `with_structured_output(Pydantic)`
for routing, research analysis, briefs, keywords and hashtags. The offline provider is a real LangChain
`BaseChatModel`. Agents stay deterministic workflows; they are **not** autonomous tool-calling (ReAct) agents.

## Options Considered

### Option A: Plain functions in LangGraph nodes + custom HTTP clients (previous design)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Cost | Lowest token use; no framework overhead |
| Scalability | Fine; parallelism would be hand-rolled |
| Team familiarity | High (plain Python) |

**Pros:** few dependencies; full control of request shapes; simple to read.
**Cons:** agent control flow invisible to LangGraph (no per-step streaming/tracing); hand-parsed JSON; custom retry
and fallback code; weaker alignment with the brief's stack.

### Option B: Agents as LangGraph subgraphs + LangChain chat models (chosen)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium: one subgraph per agent |
| Cost | Same calls as A; structured output may add a few schema tokens |
| Scalability | Built-in parallelism (`Send`, parallel branches, `graph.batch`) |
| Team familiarity | Medium; the standard stack for this course |

**Pros:** loops and parallel steps are explicit, testable graph structure; typed outputs; `with_retry`/`with_fallbacks`
and LangSmith tracing from the framework; matches the brief.
**Cons:** more framework surface (LangChain packages per provider); mock provider must be a `BaseChatModel`;
version upgrades need care.

### Option C: Autonomous LangChain/LangGraph ReAct agents (`create_react_agent`) with tools
| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium to high (prompting tools, guarding loops) |
| Cost | Higher: extra reasoning turns per step |
| Scalability | Less predictable latency |
| Team familiarity | Medium |

**Pros:** flexible; the model decides which tool to call.
**Cons:** this workflow has a known order (research → strategy → write → image), so free tool choice adds cost,
latency and nondeterminism with no benefit; harder to test.

### Option D: CrewAI / AutoGen
**Pros:** high-level "crew" abstractions. **Cons:** departs from the brief's primary stack, less control over state,
checkpointing and streaming than LangGraph.

## Trade-off Analysis
The decisive factors are alignment with the brief and making each agent's real workflow visible and testable. Option B
keeps A's determinism and cost profile while gaining framework primitives (parallelism, retries, fallbacks, structured
output, tracing). Option C's flexibility is wasted on a pipeline whose order is known in advance.

## Consequences
- Easier: adding steps to an agent (a node and an edge); seeing each step in LangSmith; testing loops and parallelism
  directly (`tests/unit/test_agents.py`); swapping providers.
- Harder: dependency management across `langchain-*` packages; contributors need LangGraph basics.
- Revisit: if a future agent needs open-ended tool use (e.g. browsing full source pages for fact-checking), that one
  agent could become a ReAct subgraph.

## Action Items
1. [x] Rebuild the six agents as subgraphs; prompts in `src/agents/prompts.py`, schemas in `src/agents/schemas.py` (PR #4)
2. [x] Replace the HTTP chat clients with `LLMGateway` (PR #4)
3. [x] Tests for subgraph structure, parallel research, loops, and the real `ChatOpenAI` client against a local server
4. [ ] Run `make bench-live` with real keys to confirm token/cost estimates
