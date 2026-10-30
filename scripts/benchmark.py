"""Performance benchmark: latency, cost, reliability and quality per provider configuration.

Runs a fixed set of content scenarios end to end through the real LangGraph
workflow and writes a Markdown + JSON report.

    python -m scripts.benchmark --mock                       # offline baseline (no keys)
    python -m scripts.benchmark --label balanced              # uses keys from .env
    python -m scripts.benchmark --label claude-first --llm anthropic --runs 3
    python -m scripts.benchmark --label lean --llm openai --research serpapi --image dalle2

Results land in docs/benchmarks/<label>.md and .json; paste the summary row into
docs/service_comparison.md to compare configurations.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.config import load_settings  # noqa: E402
from src.core.workflow import ContentBlitzEngine  # noqa: E402

SCENARIOS: List[Dict[str, str]] = [
    {"name": "research", "prompt": "Research the latest trends in sustainable packaging for e-commerce"},
    {"name": "blog", "prompt": "Write an SEO blog post about remote employee onboarding"},
    {"name": "linkedin", "prompt": "Write a LinkedIn post about hybrid work"},
    {"name": "image", "prompt": "Generate an image of a modern co-working space"},
    {"name": "campaign", "prompt": "Create a campaign about urban beekeeping"},
]
LLMS = ["openai", "anthropic", "gemini"]
SEARCH = ["serpapi", "perplexity", "tavily"]
IMAGES = ["dalle3", "dalle2", "stability"]


def _order(primary: Optional[str], options: List[str]) -> Optional[List[str]]:
    return [primary] + [o for o in options if o != primary] if primary else None


def build_engine(args: argparse.Namespace) -> ContentBlitzEngine:
    overrides: Dict[str, Any] = {"app": {"use_mock": bool(args.mock), "log_level": "WARNING"}}
    chains = {k: v for k, v in {"llm": _order(args.llm, LLMS), "research": _order(args.research, SEARCH),
                                "image": _order(args.image, IMAGES)}.items() if v}
    if chains:
        overrides["fallback_chains"] = chains
    return ContentBlitzEngine(load_settings(overrides=overrides))


def run_scenario(engine: ContentBlitzEngine, scenario: Dict[str, str], run: int) -> Dict[str, Any]:
    tracker = engine.services.tracker
    before = len(tracker.records)
    engine.services.cache.clear()  # measure cold runs, not cache hits
    started = time.perf_counter()
    state = engine.run(scenario["prompt"], thread_id=f"bench-{scenario['name']}-{run}-{time.time_ns()}")
    elapsed = time.perf_counter() - started
    records = tracker.records[before:]
    llm = [r for r in records if r.kind == "llm"]
    quality = {k: (state.get(k) or {}).get("quality", {}).get("score") for k in ("research", "blog", "linkedin", "image")
               if state.get(k) and any(t["agent"] == k for t in state.get("trace", []))}
    return {
        "scenario": scenario["name"],
        "run": run,
        "latency_s": round(elapsed, 2),
        "agent_latency_s": {t["agent"]: t.get("duration_s") for t in state.get("trace", [])},
        "llm_calls": sum(1 for r in llm if r.ok),
        "failed_attempts": sum(1 for r in records if not r.ok),
        "tokens": sum(r.input_tokens + r.output_tokens for r in llm),
        "cost_usd": round(sum(r.cost_usd for r in records), 4),
        "providers": sorted({r.provider for r in records if r.ok}),
        "quality": quality,
        "errors": [e["agent"] for e in state.get("errors", [])],
    }


def summarise(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    by: Dict[str, List[Dict[str, Any]]] = {}
    for r in results:
        by.setdefault(r["scenario"], []).append(r)
    rows = {}
    for name, rs in by.items():
        q_vals = [v for r in rs for v in r["quality"].values() if v is not None]
        rows[name] = {
            "runs": len(rs),
            "latency_p50_s": round(statistics.median(r["latency_s"] for r in rs), 2),
            "latency_max_s": round(max(r["latency_s"] for r in rs), 2),
            "llm_calls": round(statistics.mean(r["llm_calls"] for r in rs), 1),
            "tokens": round(statistics.mean(r["tokens"] for r in rs)),
            "cost_usd": round(statistics.mean(r["cost_usd"] for r in rs), 4),
            "avg_quality": round(statistics.mean(q_vals), 1) if q_vals else None,
            "failed_attempts": sum(r["failed_attempts"] for r in rs),
            "agent_errors": sum(len(r["errors"]) for r in rs),
            "providers": sorted({p for r in rs for p in r["providers"]}),
        }
    return rows


def to_markdown(label: str, meta: Dict[str, Any], rows: Dict[str, Any]) -> str:
    lines = [f"# Benchmark: {label}", "",
             f"- Date: {meta['date']}  ",
             f"- Runs per scenario: {meta['runs']}  ",
             f"- Provider chains: LLM {' → '.join(meta['chains']['llm'])}; research {' → '.join(meta['chains']['research'])}; "
             f"images {' → '.join(meta['chains']['image'])}  ",
             f"- Offline mock mode: {'yes' if meta['offline'] else 'no'}", "",
             "| Scenario | p50 latency (s) | max (s) | LLM calls | Tokens | Cost (USD) | Avg quality | Failed attempts | Agent errors |",
             "|---|---|---|---|---|---|---|---|---|"]
    for name, r in rows.items():
        lines.append(f"| {name} | {r['latency_p50_s']} | {r['latency_max_s']} | {r['llm_calls']} | {r['tokens']} | "
                     f"${r['cost_usd']:.4f} | {r['avg_quality'] if r['avg_quality'] is not None else '–'} | "
                     f"{r['failed_attempts']} | {r['agent_errors']} |")
    lines += ["", "Latency is wall-clock for one conversational turn on a cold cache. Cost uses the list prices in "
              "`src/core/resilience.py`. Quality is the mean of the 0-100 scores of the assets produced."]
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--label", help="Name for the result files (default: 'offline-mock' with --mock, else 'live')")
    p.add_argument("--mock", action="store_true", help="Offline mock providers")
    p.add_argument("--runs", type=int, default=3)
    p.add_argument("--llm", choices=LLMS, help="Primary LLM (others become fallbacks)")
    p.add_argument("--research", choices=SEARCH, help="Primary research engine")
    p.add_argument("--image", choices=IMAGES, help="Primary image provider")
    p.add_argument("--scenarios", nargs="*", choices=[s["name"] for s in SCENARIOS])
    p.add_argument("--out", default=str(ROOT / "docs" / "benchmarks"))
    args = p.parse_args(argv)
    label = args.label or ("offline-mock" if args.mock else "live")

    engine = build_engine(args)
    scenarios = [s for s in SCENARIOS if not args.scenarios or s["name"] in args.scenarios]
    results = []
    for s in scenarios:
        for i in range(args.runs):
            r = run_scenario(engine, s, i)
            results.append(r)
            print(f"{s['name']:<9} run {i + 1}/{args.runs}: {r['latency_s']}s, {r['llm_calls']} LLM calls, "
                  f"${r['cost_usd']:.4f}, quality {r['quality']}")
    usage = engine.usage()
    meta = {"label": label, "date": time.strftime("%Y-%m-%d"), "runs": args.runs, "offline": engine.services.is_offline,
            "chains": usage["providers"]}
    rows = summarise(results)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{label}.json").write_text(json.dumps({"meta": meta, "summary": rows, "results": results}, indent=2))
    (out / f"{label}.md").write_text(to_markdown(label, meta, rows))
    print(f"\nWrote {out / (label + '.md')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
