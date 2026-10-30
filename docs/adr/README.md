# Architecture Decision Records

Each ADR records one significant decision: the context, the options considered, the trade-offs and the consequences.
New decisions get the next number; a decision that is replaced is marked **Superseded** and links to its replacement.

| # | Title | Status | Date |
|---|---|---|---|
| [0001](0001-agents-as-langgraph-subgraphs-with-langchain-models.md) | Agents as LangGraph subgraphs calling LangChain chat models | Accepted (supersedes the original plain-function agents) | 2026-10-29 |
| [0002](0002-react-fastapi-sse-ui.md) | React SPA + FastAPI with Server-Sent Events instead of Streamlit | Accepted | 2026-10-28 |
| [0003](0003-provider-retry-and-fallback-strategy.md) | Retry transient errors per provider, then fall back across providers, offline last | Accepted | 2026-10-29 |
| [0004](0004-deterministic-fact-checking.md) | Deterministic source credibility and claim verification | Accepted | 2026-10-29 |
| [0005](0005-conversation-memory.md) | Conversation memory with LangGraph checkpointers | Accepted | 2026-10-28 |

Template: see any ADR above (Status, Date, Deciders, Context, Decision, Options Considered, Trade-off Analysis,
Consequences, Action Items).
