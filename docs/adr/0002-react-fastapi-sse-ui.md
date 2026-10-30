# ADR-0002: React SPA + FastAPI with Server-Sent Events instead of Streamlit

**Status:** Accepted (supersedes the original Streamlit UI)
**Date:** 2026-10-28
**Deciders:** Prasanna Koppolu (project owner)

## Context
The brief lists Streamlit as the primary web interface with React, Gradio, Vue and Flask as alternatives, and grades
interface design (7%) and conversation flow (3%). The UI needs live per-agent progress, side-by-side editing with
instant re-scoring, a research panel with citations, exports, settings, and must work on mobile. The Streamlit
prototype rerendered the whole page on each interaction, had limited layout control and could not stream progress
cleanly while keeping the editor usable.

## Decision
A React + TypeScript SPA (Vite) served by a FastAPI backend. The chat endpoint streams progress with
**Server-Sent Events**; other operations are JSON REST. In production one uvicorn process serves both the API and the
built SPA from one origin.

## Options Considered

### Option A: Streamlit (previous)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low (Python only) |
| Cost | Lowest build effort |
| Scalability | Session state per server process; reruns per interaction |
| Team familiarity | High |

**Pros:** fastest to build; one language. **Cons:** limited layout and interaction control, awkward streaming, weaker
responsive design, UI tied to the server process.

### Option B: React SPA + FastAPI + SSE (chosen)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Medium: two codebases (TypeScript + Python) |
| Cost | More build effort; same runtime cost |
| Scalability | Stateless API; replicas behind a proxy with shared memory |
| Team familiarity | High for web engineers |

**Pros:** full control of UX (live pipeline, editors, badges), proper responsive design, typed client, reusable API,
standard deployment. **Cons:** a second toolchain (Node) and test stack (Vitest).

### Option C: Gradio
**Pros:** quick ML demos. **Cons:** same layout limits as Streamlit for a multi-panel product UI.

### Streaming sub-decision: SSE vs WebSockets vs polling
SSE fits one-way progress events, works through standard proxies and needs no extra protocol; WebSockets add
bidirectional complexity we don't need; polling adds latency and load.

## Trade-off Analysis
The UX requirements (live pipeline, editing, mobile) outweigh the cost of a second codebase. Keeping the API separate
also enables the CLI, benchmarks and future clients to share one engine.

## Consequences
- Easier: UI iteration, accessibility and responsive layout; Playwright browser tests; split hosting if needed.
- Harder: two dependency trees; API contract must stay in sync with `frontend/src/types.ts`.
- Revisit: if real-time collaboration is needed, move to WebSockets.

## Action Items
1. [x] FastAPI with REST + SSE and SPA hosting (PR #2)
2. [x] React app with Vitest and Playwright tests; Streamlit removed (PR #2)
3. [ ] Generate TypeScript types from the OpenAPI schema to remove manual type syncing
