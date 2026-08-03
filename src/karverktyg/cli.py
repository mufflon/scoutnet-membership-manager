"""Command-line entrypoint: serve the app and run the read-only scheduled jobs."""

from __future__ import annotations

import argparse
import sys

from karverktyg.settings import Mode, Settings


def _settings(mode: str | None) -> Settings:
    return Settings(mode=Mode(mode)) if mode else Settings()


def _serve(args: argparse.Namespace) -> int:
    from karverktyg.web import create_app

    app = create_app(_settings(args.mode))
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


def _canary(args: argparse.Namespace) -> int:
    from karverktyg.jobs.canary import run_canary

    result = run_canary(_settings(args.mode))
    print(result.render())
    return 0 if result.ok else 1


def _drift(args: argparse.Namespace) -> int:
    from karverktyg.jobs.spec_drift import run_drift_check

    result = run_drift_check()
    print(result.render())
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="karverktyg")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("serve", help="run the HTTP service")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--mode", default=None, help="fixture | read_only | read_write")
    s.add_argument("--debug", action="store_true")
    s.set_defaults(func=_serve)

    c = sub.add_parser("canary", help="read-only canary check (§14)")
    c.add_argument("--mode", default="read_only")
    c.set_defaults(func=_canary)

    d = sub.add_parser("drift-check", help="OpenAPI spec drift check (§14)")
    d.add_argument("--mode", default=None)
    d.set_defaults(func=_drift)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
