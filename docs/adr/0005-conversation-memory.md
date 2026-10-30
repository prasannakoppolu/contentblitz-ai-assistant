# ADR-0005: Conversation memory with LangGraph checkpointers

**Status:** Accepted
**Date:** 2026-10-28
**Deciders:** Prasanna Koppolu (project owner)

## Context
The brief requires "conversation memory and context preservation across interactions" (State Management: LangGraph
Memory; Redis, MongoDB, PostgreSQL as alternatives), and the FAQ recommends LangGraph's persistence layer. Follow-ups
("make it shorter", "turn it into a LinkedIn post") need prior research, drafts and history. The app should run with
zero infrastructure for evaluators, but a deployed instance should not lose conversations on restart.

## Decision
Use LangGraph checkpointers keyed by `thread_id`: `MemorySaver` by default and `SqliteSaver` when
`CONTENTBLITZ_MEMORY=sqlite` (the Docker default, on the `/data` volume). All engines in the API share one
checkpointer, so changing provider settings keeps the conversation. Artefacts in state are tagged with their topic so
stale ones are not reused. For multiple replicas, pass LangGraph's `PostgresSaver`.

## Options Considered

### Option A: LangGraph checkpointer (Memory/SQLite, Postgres when scaling) (chosen)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low; built into graph compilation |
| Cost | None (in-process / local file) |
| Scalability | Single instance with SQLite; Postgres for many |
| Team familiarity | Medium |

**Pros:** state and graph stay consistent (checkpoint per step); human edits via `update_state`; no extra service.
**Cons:** SQLite is single-node; state schema changes need care.

### Option B: Redis session store
**Pros:** fast, shared across replicas. **Cons:** extra infrastructure; duplicates what LangGraph already does; manual
serialisation of graph state.

### Option C: Browser-side storage
**Pros:** no server state. **Cons:** large state over the wire each turn; lost when storage is cleared; not usable by
the CLI or benchmarks.

## Trade-off Analysis
A matches the brief and keeps zero-infrastructure local runs, with a clear upgrade path (Postgres) that doesn't change
application code.

## Consequences
- Easier: multi-turn refinement, restoring a conversation on reload, persisting human edits.
- Harder: horizontal scaling needs a shared checkpointer and shared image storage.
- Revisit: retention/cleanup of old threads; Postgres saver when running more than one replica.

## Action Items
1. [x] Checkpointer per `thread_id`, shared across engines; SQLite option and Docker default (PR #2)
2. [ ] Thread retention policy (delete threads older than N days)
3. [ ] Document and test `PostgresSaver` wiring for multi-replica deployments
