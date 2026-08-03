"""
Database bootstrap for deploys (build-up).

Brings the database to the current schema, reusing an existing one when possible:

* empty DB            -> run migrations (fresh install);
* alembic-managed DB  -> ``alembic upgrade head`` (apply pending migrations);
* unmanaged existing DB (e.g. created by ``create_all``) that matches the model
  -> stamp + upgrade (adopt in place, data kept);
* incompatible DB, migration not possible -> keep as much as possible (the
  application's own data: email templates) and nuke everything superfluous, then
  rebuild the current schema and restore the templates.

Idempotent — safe to run on every deploy (used as an init step).
"""

from __future__ import annotations

from dataclasses import dataclass

from alembic import command
from alembic.config import Config
from sqlalchemy import MetaData, inspect, text

from karverktyg.db.models import Base, EmailTemplate
from karverktyg.db.session import get_session, make_engine, make_sessionmaker


class IncompatibleSchema(RuntimeError):
    """The existing schema cannot be migrated in place."""


@dataclass
class BootstrapResult:
    """Outcome of a bootstrap run."""

    action: str  # initialised | upgraded | adopted | rebuilt
    detail: str
    templates_preserved: int = 0

    def render(self) -> str:
        """One-line summary for logs."""
        line = f"db-bootstrap: {self.action} — {self.detail}"
        if self.templates_preserved:
            line += f" (preserved {self.templates_preserved} template(s))"
        return line


def _alembic_cfg(database_url: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _assert_compatible(insp: object) -> None:
    """Every model table must exist with at least its model columns."""
    existing = set(insp.get_table_names())
    for table in Base.metadata.tables.values():
        if table.name not in existing:
            raise IncompatibleSchema(f"missing table {table.name!r}")
        cols = {c["name"] for c in insp.get_columns(table.name)}
        missing = {c.name for c in table.columns} - cols
        if missing:
            raise IncompatibleSchema(f"table {table.name!r} missing columns {sorted(missing)}")


def _dump_templates(engine: object) -> list[dict]:
    if "email_template" not in inspect(engine).get_table_names():
        return []
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT template_key, subject, body, updated_by FROM email_template")
        ).mappings()
        return [dict(r) for r in rows]


def _drop_everything(engine: object) -> None:
    """Drop all tables, including any superfluous ones not in our metadata."""
    md = MetaData()
    md.reflect(bind=engine)
    md.drop_all(bind=engine)


def _restore_templates(engine: object, templates: list[dict]) -> None:
    factory = make_sessionmaker(engine)
    with get_session(factory) as s:
        for t in templates:
            s.add(
                EmailTemplate(
                    template_key=t["template_key"],
                    subject=t["subject"],
                    body=t["body"],
                    updated_by=t.get("updated_by"),
                )
            )


def bootstrap(database_url: str) -> BootstrapResult:
    """Bring the database to the current schema, reusing it when possible (§9)."""
    engine = make_engine(database_url)
    cfg = _alembic_cfg(database_url)
    tables = set(inspect(engine).get_table_names())

    if not tables:
        command.upgrade(cfg, "head")
        return BootstrapResult("initialised", "fresh database, migrations applied")

    if "alembic_version" in tables:
        command.upgrade(cfg, "head")
        return BootstrapResult("upgraded", "migration-managed database brought to head")

    # Unmanaged existing database. Adopt it if the schema matches the model.
    try:
        _assert_compatible(inspect(engine))
        command.stamp(cfg, "head")
        command.upgrade(cfg, "head")
    except IncompatibleSchema as e:
        templates = _dump_templates(engine)
        _drop_everything(engine)
        command.upgrade(cfg, "head")
        _restore_templates(engine, templates)
        return BootstrapResult(
            "rebuilt",
            f"incompatible ({e}); superfluous data removed",
            templates_preserved=len(templates),
        )
    else:
        return BootstrapResult("adopted", "existing compatible database kept in place")
