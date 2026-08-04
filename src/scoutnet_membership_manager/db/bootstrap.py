"""
Database bootstrap for deploys (build-up).

Brings the database to the current schema, reusing an existing one when possible:

* empty DB            -> run migrations (fresh install);
* alembic-managed DB  -> ``alembic upgrade head``; if that actually advances the
  revision, the uppflyttning working state is cleared (see below);
* unmanaged existing DB (e.g. created by ``create_all``) that matches the model
  -> stamp + upgrade with nothing to migrate (adopt in place, data kept);
* incompatible DB, migration not possible -> keep the meaningful data (email
  templates, finding acks, message log, and write run/journal/snapshot history),
  rebuild the current schema, and drop everything else.

**Uppflyttning working state is never kept across a migration or a rebuild.**
It is per-cohort-year scratch data, and a version bump may itself be prompted by
an incompatibility, so ``uppflyttning_entry`` and ``cohort_target`` are cleared
whenever migrations are applied. An ordinary redeploy that applies no migration
leaves them untouched, so in-progress decisions survive normal restarts.

Idempotent — safe to run on every deploy (used as an init step).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, MetaData, inspect, text

from scoutnet_membership_manager.db.models import (
    Base,
    EmailTemplate,
    FindingAck,
    MessageLog,
    Snapshot,
    WriteJournal,
    WriteRun,
)
from scoutnet_membership_manager.db.session import get_session, make_engine, make_sessionmaker

# Per-year uppflyttning scratch. Cleared only when a migration actually advances
# the revision (see bootstrap: the DELETE is gated on before != after), or on a
# rebuild — never on a plain redeploy that finds the DB already at head.
#
# The write tables are deliberately NOT here. An in-flight run's journal is the
# resume-after-crash recovery path, so it must survive every case: a crash
# restart, a no-op redeploy, a revision-advancing migration AND a rebuild. Being
# absent from this tuple keeps it untouched by the scratch-clear; being present
# in _MEANINGFUL below keeps it across a rebuild too. It is never wiped here.
_UPPFLYTTNING_TABLES = ("uppflyttning_entry", "cohort_target")

# Meaningful data preserved across a rebuild: (model, carried columns).
_MEANINGFUL = {
    "email_template": (EmailTemplate, ["template_key", "subject", "body", "updated_by"]),
    "finding_ack": (FindingAck, ["member_no", "finding_type", "value_hash", "acknowledged_by"]),
    "message_log": (MessageLog, ["member_no", "message_type"]),
    # Write history: a run's journal is the recovery path (undo/reconcile) once
    # it has touched real records, so it is meaningful, not scratch (§8, §9).
    # write_journal.id is autoincrement and intentionally not carried.
    "write_run": (
        WriteRun,
        ["id", "kind", "cohort_year", "parent_run_id", "mode", "state", "snapshot_id"],
    ),
    "write_journal": (
        WriteJournal,
        [
            "run_id",
            "chunk_id",
            "member_no",
            "intended_status",
            "intended_troop_id",
            "source_troop_id",
            "state",
            "attempts",
            "error",
        ],
    ),
    "snapshot": (Snapshot, ["id", "run_id", "path", "size_bytes"]),
}


class IncompatibleSchema(RuntimeError):
    """The existing schema cannot be migrated in place."""


@dataclass
class BootstrapResult:
    """Outcome of a bootstrap run."""

    action: str  # initialised | upgraded | adopted | rebuilt
    detail: str
    preserved: dict[str, int] = field(default_factory=dict)

    def render(self) -> str:
        """One-line summary for logs."""
        line = f"db-bootstrap: {self.action} — {self.detail}"
        if self.preserved:
            kept = ", ".join(f"{name}×{n}" for name, n in self.preserved.items())
            line += f" (kept {kept})"
        return line


def _alembic_cfg(database_url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _revision(engine: Engine) -> str | None:
    if "alembic_version" not in inspect(engine).get_table_names():
        return None
    with engine.connect() as conn:
        row = conn.execute(text("SELECT version_num FROM alembic_version")).first()
    return row[0] if row else None


def _assert_compatible(engine: Engine) -> None:
    """Every model table must exist with at least its model columns."""
    insp = inspect(engine)
    existing = set(insp.get_table_names())
    for table in Base.metadata.tables.values():
        if table.name not in existing:
            raise IncompatibleSchema(f"missing table {table.name!r}")
        cols = {c["name"] for c in insp.get_columns(table.name)}
        missing = {c.name for c in table.columns} - cols
        if missing:
            raise IncompatibleSchema(f"table {table.name!r} missing columns {sorted(missing)}")


def _clear_uppflyttning(engine: Engine) -> None:
    existing = set(inspect(engine).get_table_names())
    with engine.begin() as conn:
        for table in _UPPFLYTTNING_TABLES:
            if table in existing:
                conn.execute(text(f"DELETE FROM {table}"))  # noqa: S608 - fixed table names


def _dump_meaningful(engine: Engine) -> dict[str, tuple[type, list[dict]]]:
    insp = inspect(engine)
    existing = set(insp.get_table_names())
    dumped: dict[str, tuple[type, list[dict]]] = {}
    for table, (model, cols) in _MEANINGFUL.items():
        if table not in existing:
            continue
        have = {c["name"] for c in insp.get_columns(table)}
        usable = [c for c in cols if c in have]
        if not usable:
            continue
        with engine.connect() as conn:
            rows = conn.execute(text(f"SELECT {', '.join(usable)} FROM {table}")).mappings()  # noqa: S608
            dumped[table] = (model, [dict(r) for r in rows])
    return dumped


def _restore_meaningful(
    engine: Engine, dumped: dict[str, tuple[type, list[dict]]]
) -> dict[str, int]:
    counts: dict[str, int] = {}
    factory = make_sessionmaker(engine)
    with get_session(factory) as s:
        for table, (model, rows) in dumped.items():
            for r in rows:
                s.add(model(**r))
            counts[table] = len(rows)
    return counts


def _drop_everything(engine: Engine) -> None:
    """Drop all tables, including any superfluous ones not in our metadata."""
    md = MetaData()
    md.reflect(bind=engine)
    md.drop_all(bind=engine)


def bootstrap(database_url: str) -> BootstrapResult:
    """Bring the database to the current schema, reusing it when possible (§9)."""
    engine = make_engine(database_url)
    cfg = _alembic_cfg(database_url)
    tables = set(inspect(engine).get_table_names())

    if not tables:
        command.upgrade(cfg, "head")
        return BootstrapResult("initialised", "fresh database, migrations applied")

    if "alembic_version" in tables:
        before = _revision(engine)
        command.upgrade(cfg, "head")
        after = _revision(engine)
        if before != after:
            _clear_uppflyttning(engine)
            return BootstrapResult("upgraded", f"migrated {before}->{after}; uppflyttning cleared")
        return BootstrapResult("upgraded", "already at head; nothing to migrate")

    # Unmanaged existing database. Adopt it if the schema matches the model.
    try:
        _assert_compatible(engine)
        command.stamp(cfg, "head")
        command.upgrade(cfg, "head")
    except IncompatibleSchema as e:
        preserved_data = _dump_meaningful(engine)
        _drop_everything(engine)
        command.upgrade(cfg, "head")
        counts = _restore_meaningful(engine, preserved_data)
        return BootstrapResult(
            "rebuilt",
            f"incompatible ({e}); uppflyttning discarded, meaningful data kept",
            preserved=counts,
        )
    else:
        return BootstrapResult("adopted", "existing compatible database kept in place")
