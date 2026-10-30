# ADR-0004: Deterministic source credibility and claim verification

**Status:** Accepted
**Date:** 2026-10-29
**Deciders:** Prasanna Koppolu (project owner)

## Context
The brief lists "Source Credibility: implementing robust fact-checking and source verification to maintain content
reliability and avoid misinformation" as a key challenge, and grades research quality "with proper source attribution"
(10%). Research already required `[n]` citations, but nothing checked that a citation supports its claim or that the
source is trustworthy. Any check runs on every research turn, so cost and latency matter.

## Decision
Add a `verify` node to the research subgraph using `src/utils/source_verification.py`:
- **Credibility per source:** tiers by domain type and known publishers (government/academic and research publishers
  high, established industry media medium, user-generated platforms low), adjusted for recency and HTTPS.
- **Claim verification:** for each finding and statistic, the `[n]` citation must exist, the cited source must share
  the claim's key terms, and every figure in the claim must appear in that source. Statuses: supported, weak,
  unverified, uncited, invalid citation.
- Results appear as badges in the Research tab and as two research-quality dimensions.

## Options Considered

### Option A: No verification (citations only)
**Pros:** zero cost. **Cons:** doesn't address the brief's challenge; fabricated statistics go unnoticed.

### Option B: Deterministic checks against search snippets (chosen)
| Dimension | Assessment |
|-----------|------------|
| Complexity | Low |
| Cost | Free, milliseconds |
| Scalability | Runs on every turn |
| Team familiarity | High |

**Pros:** explainable, testable, no extra API calls; catches the most damaging error (numbers not in the source).
**Cons:** snippets are short, so "unverified" means "confirm in the full source", not "false"; term overlap is a
heuristic; the domain list needs upkeep.

### Option C: LLM-as-judge over full source pages
| Dimension | Assessment |
|-----------|------------|
| Complexity | High (page fetching, extraction, prompting) |
| Cost | Extra LLM calls and fetches per claim |
| Scalability | Adds seconds per research turn |
| Team familiarity | Medium |

**Pros:** semantic judgement on full text. **Cons:** cost, latency, nondeterminism, and the judge can also be wrong.

## Trade-off Analysis
B delivers most of the value at no cost and keeps tests deterministic; its weakness (snippet-level evidence) is made
explicit in the UI wording. C is the natural upgrade for teams that need stronger guarantees.

## Consequences
- Easier: spotting unsupported statistics before publishing; explaining a research score.
- Harder: offline demo data is flagged heavily (generic demo snippets), which needs explaining in demos.
- Revisit: credibility tiers as data in config; an optional LLM-as-judge step for flagged claims only.

## Action Items
1. [x] `verify` node, credibility tiers, claim statuses, UI badges (PR #4)
2. [ ] Move the publisher lists into `config/services.yaml`
3. [ ] Optional LLM-as-judge on `unverified`/`weak` claims using full page text
