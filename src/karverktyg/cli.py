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
    print(result.render())  # noqa: T201
    return 0 if result.ok else 1


def _drift(_args: argparse.Namespace) -> int:
    from karverktyg.jobs.spec_drift import run_drift_check

    result = run_drift_check()
    print(result.render())  # noqa: T201
    return 0


def _build_rw(settings: Settings) -> tuple[object, object]:
    """Return (client, sessionmaker) for a read_write run — a seam tests replace."""
    from karverktyg.web import create_app

    app = create_app(settings)
    return app.config["SCOUTNET"], app.config["SESSIONMAKER"]


def _print_result(result: object) -> None:
    print(f"run: mode={result.mode} state={result.run_state} run_id={result.run_id}")  # noqa: T201
    for p in result.preflight:
        print(  # noqa: T201
            f"  {p.move.member_no}: {p.category} "
            f"(troop {p.current_troop_id} -> {p.move.target_troop_id}) {p.reason}"
        )
    if result.reconcile is not None:
        print(f"reconcile: {result.reconcile}")  # noqa: T201
    if result.failed_chunk is not None:
        print(f"FAILED at chunk {result.failed_chunk}: {result.error}")  # noqa: T201


def _check_idempotency(client: object, member: str, target: int) -> int:
    """Re-apply the same move once and confirm the endpoint treats it as a no-op (§8)."""
    from karverktyg.scoutnet.client import ScoutnetError
    from karverktyg.write.executor import write_status_token

    live = client.memberlist("active", fresh=True).by_member_no().get(member)
    payload = {
        member: {
            "status": write_status_token(live.status_code if live else None),
            "troop_id": target,
        }
    }
    try:
        client.update_membership(payload)
    except ScoutnetError as e:
        print(f"idempotency FAILED: re-applying the move errored: {e}", file=sys.stderr)  # noqa: T201
        return 1
    print("idempotency OK: re-applying the same move was accepted as a no-op.")  # noqa: T201
    return 0


def _verify_write(args: argparse.Namespace) -> int:  # noqa: PLR0911 - guard-heavy CLI handler
    """
    Stage-2 verification (§8): a single-member write against the real API, on a
    record nobody depends on (the placeholder account). Dry-run by default.
    """
    from karverktyg.scoutnet.client import ScoutnetError
    from karverktyg.write import IntendedMove, RunMode, WriteExecutor
    from karverktyg.write.executor import AllowlistViolation, ExecutorError

    settings = _settings(args.mode)
    if settings.mode is not Mode.READ_WRITE:
        print("verify-write requires SCOUTNET_MODE=read_write", file=sys.stderr)  # noqa: T201
        return 2
    if not args.undo_run and (not args.member or args.to is None):
        print("verify-write needs --member and --to, or --undo-run", file=sys.stderr)  # noqa: T201
        return 2

    client, sm = _build_rw(settings)
    executor = WriteExecutor(client, settings, sm)
    mode = RunMode.EXECUTE if args.execute else RunMode.DRY_RUN
    try:
        if args.undo_run:
            result = executor.undo(args.undo_run, mode=mode)
        else:
            member = client.memberlist("active", fresh=True).by_member_no().get(args.member)
            if member is None:
                print(f"member {args.member} not in active roster", file=sys.stderr)  # noqa: T201
                return 2
            moves = [IntendedMove(args.member, member.unit_troop_id, args.to)]
            result = executor.run(moves, kind="stage2_verify", mode=mode)
    except (AllowlistViolation, ExecutorError, ScoutnetError) as e:
        print(f"verify-write failed: {e}", file=sys.stderr)  # noqa: T201
        return 1

    _print_result(result)
    if mode is RunMode.DRY_RUN:
        print("\nDry-run only — nothing written. Re-run with --execute to perform.")  # noqa: T201
        return 0
    if not args.undo_run:
        print(  # noqa: T201
            f"\nExecuted run {result.run_id}. Verify by hand in the Scoutnet UI that member "
            f"{args.member} is now in troop {args.to}, then undo with:\n"
            f"  karverktyg verify-write --undo-run {result.run_id} --execute"
        )
        if args.idempotency:
            return _check_idempotency(client, args.member, args.to)
    return 0 if result.run_state == "done" else 1


def _db_bootstrap(args: argparse.Namespace) -> int:
    from karverktyg.db.bootstrap import bootstrap

    settings = _settings(args.mode)
    if not settings.database_url:
        print("db-bootstrap: no SCOUTNET_DATABASE_URL configured", file=sys.stderr)  # noqa: T201
        return 2
    print(bootstrap(settings.database_url).render())  # noqa: T201
    return 0


def _validate_config(args: argparse.Namespace) -> int:
    """Validate a kår-config JSON against the model/schema (§13)."""
    from karverktyg.config.loader import ConfigError, load_config

    try:
        cfg = load_config(args.path)
    except ConfigError as e:
        print(f"✗ {e}", file=sys.stderr)  # noqa: T201
        return 1
    print(f"✓ {args.path}: giltig (v{cfg.version}, {len(cfg.avdelningar)} avdelningar)")  # noqa: T201
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main."""
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

    b = sub.add_parser("db-bootstrap", help="migrate/adopt the database (build-up)")
    b.add_argument("--mode", default=None)
    b.set_defaults(func=_db_bootstrap)

    v = sub.add_parser("verify-write", help="stage-2 single-member write verification (§8)")
    v.add_argument("--mode", default=None)
    v.add_argument("--member", default=None, help="member_no to move (must be on the allowlist)")
    v.add_argument("--to", type=int, default=None, help="target troop_id")
    v.add_argument("--undo-run", dest="undo_run", default=None, help="undo a run by id instead")
    v.add_argument("--execute", action="store_true", help="perform the write (default: dry-run)")
    v.add_argument("--idempotency", action="store_true", help="re-apply once, expect a no-op")
    v.set_defaults(func=_verify_write)

    vc = sub.add_parser("validate-config", help="validate a kår-config JSON against the schema")
    vc.add_argument("path", help="path to the config JSON")
    vc.set_defaults(func=_validate_config)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
