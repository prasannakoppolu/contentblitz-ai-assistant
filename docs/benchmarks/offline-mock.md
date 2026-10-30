# Benchmark: offline-mock

- Date: 2026-10-29  
- Runs per scenario: 3  
- Provider chains: LLM mock; research mock; images placeholder  
- Offline mock mode: yes

| Scenario | p50 latency (s) | max (s) | LLM calls | Tokens | Cost (USD) | Avg quality | Failed attempts | Agent errors |
|---|---|---|---|---|---|---|---|---|
| research | 0.02 | 1.49 | 4 | 3239 | $0.0000 | 83 | 0 | 0 |
| blog | 0.04 | 0.04 | 5 | 4320 | $0.0000 | 87.5 | 0 | 0 |
| linkedin | 0.04 | 0.04 | 5 | 2590 | $0.0000 | 89.5 | 0 | 0 |
| image | 0.02 | 0.05 | 2 | 556 | $0.0000 | 80 | 0 | 0 |
| campaign | 0.06 | 0.06 | 10 | 6891 | $0.0000 | 88.2 | 0 | 0 |

Latency is wall-clock for one conversational turn on a cold cache. Cost uses the list prices in `src/core/resilience.py`. Quality is the mean of the 0-100 scores of the assets produced.
