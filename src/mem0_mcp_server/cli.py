"""mem-cli: minimal command-line interface for the mem-server."""

from __future__ import annotations

import argparse
import json
import os
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mem-cli",
        description="Command-line interface for the mem-server.",
    )
    parser.add_argument(
        "--server",
        default=os.getenv("MEM_SERVER_URL", "http://localhost:8081"),
        help="mem-server base URL",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("MEM_TOKEN", ""),
        help="Bearer token for authentication",
    )

    sub = parser.add_subparsers(dest="command")

    sub.add_parser("whoami", help="Show current identity")

    search_p = sub.add_parser("search", help="Search memories")
    search_p.add_argument("query", help="Natural language search query")

    add_p = sub.add_parser("add", help="Add a memory")
    add_p.add_argument("text", help="Text to remember")

    sub.add_parser("doctor", help="Run connectivity diagnostics")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Minimal stub implementations — real HTTP calls come later
    if args.command == "whoami":
        print(json.dumps({"status": "ok", "command": "whoami"}))
    elif args.command == "search":
        print(json.dumps({"status": "ok", "command": "search", "query": args.query}))
    elif args.command == "add":
        print(json.dumps({"status": "ok", "command": "add", "text": args.text}))
    elif args.command == "doctor":
        print(json.dumps({"status": "ok", "command": "doctor"}))


if __name__ == "__main__":
    main()
