"""Command-line interface.

    python -m src.cli "Create a campaign about sustainable packaging" --mock
    python -m src.cli --interactive --mock
"""
from __future__ import annotations

import argparse
import sys

from src.core.config import load_settings
from src.core.workflow import ContentBlitzEngine


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ContentBlitz multi-agent content assistant")
    parser.add_argument("query", nargs="?", help="Content request")
    parser.add_argument("--mock", action="store_true", help="Run fully offline with mock providers")
    parser.add_argument("--interactive", "-i", action="store_true", help="Multi-turn chat in the terminal")
    parser.add_argument("--thread", default="cli", help="Conversation thread id")
    args = parser.parse_args(argv)

    overrides = {"app": {"use_mock": True}} if args.mock else None
    engine = ContentBlitzEngine(load_settings(overrides=overrides))
    print(f"Providers: {engine.usage()['providers']}\n")

    def turn(q: str) -> None:
        for _node, update in engine.stream(q, args.thread):
            for t in (update.get("trace") or [])[-1:]:
                print(f"  ▸ {t['agent']}: {t['status']} {t['detail']}")
        print("\n" + engine.get_state(args.thread).get("response", "") + "\n")

    if args.interactive:
        print("ContentBlitz interactive mode. Type 'exit' to quit.")
        while True:
            try:
                q = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if q.lower() in {"exit", "quit"}:
                break
            if q:
                turn(q)
        return 0
    if not args.query:
        parser.print_help()
        return 1
    turn(args.query)
    print(f"Usage: {engine.usage()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
