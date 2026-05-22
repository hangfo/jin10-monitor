"""Start the standalone Jin10 Monitor dashboard."""

from __future__ import annotations

import argparse

import uvicorn


ALLOWED_HOSTS = {"127.0.0.1", "localhost"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start the local Jin10 dashboard.")
    parser.add_argument("--host", default="127.0.0.1", help="Dashboard host; localhost only.")
    parser.add_argument("--port", default=8765, type=int, help="Dashboard port.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.host not in ALLOWED_HOSTS:
        raise SystemExit("Dashboard only allows 127.0.0.1 / localhost.")
    uvicorn.run("dashboard.app:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
