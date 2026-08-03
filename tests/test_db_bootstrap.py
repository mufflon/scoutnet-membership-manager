from __future__ import annotations

from sqlalchemy import create_engine, inspect, select, text

from karverktyg.db import Base, EmailTemplate, make_sessionmaker
from karverktyg.db.bootstrap import bootstrap
from karverktyg.db.session import get_session


def _url(tmp_path):
    return f"sqlite:///{tmp_path / 'kv.db'}"


def _templates(url):
    with get_session(make_sessionmaker(create_engine(url))) as s:
        return s.execute(select(EmailTemplate)).scalars().all()


def test_bootstrap_fresh_runs_migrations(tmp_path):
    url = _url(tmp_path)
    r = bootstrap(url)
    assert r.action == "initialised"
    names = set(inspect(create_engine(url)).get_table_names())
    assert {"email_template", "cohort_target", "alembic_version"} <= names
    # 0003 write tables are part of head.
    assert {"write_run", "write_journal", "snapshot"} <= names


def test_bootstrap_rebuild_preserves_write_journal(tmp_path):
    # A journal is the recovery path (undo/reconcile) once a run has touched real
    # records, so a rebuild must preserve it, not drop it as scratch (§8, §9).
    url = _url(tmp_path)
    engine = create_engine(url)
    with engine.begin() as c:
        c.execute(
            text(
                "CREATE TABLE write_journal (id INTEGER PRIMARY KEY, run_id VARCHAR, "
                "chunk_id INTEGER, member_no VARCHAR, intended_status VARCHAR, "
                "intended_troop_id INTEGER, source_troop_id INTEGER, state VARCHAR, "
                "attempts INTEGER, error TEXT)"
            )
        )
        c.execute(
            text(
                "INSERT INTO write_journal (run_id, chunk_id, member_no, intended_status, "
                "intended_troop_id, state, attempts) "
                "VALUES ('run-1', 0, '1000', 'confirmed', 12345, 'done', 1)"
            )
        )
        c.execute(text("CREATE TABLE junk (id INTEGER PRIMARY KEY)"))  # forces incompatible

    r = bootstrap(url)
    assert r.action == "rebuilt"
    assert r.preserved["write_journal"] == 1

    with engine.connect() as c:
        row = c.execute(
            text("SELECT member_no, intended_troop_id, run_id FROM write_journal")
        ).first()
    assert row == ("1000", 12345, "run-1")


def test_bootstrap_adopts_compatible_createall_db(tmp_path):
    url = _url(tmp_path)
    engine = create_engine(url)
    Base.metadata.create_all(engine)  # unmanaged (no alembic_version), matches model
    with get_session(make_sessionmaker(engine)) as s:
        s.add(EmailTemplate(template_key="scout_request", subject="keep", body="b"))

    r = bootstrap(url)
    assert r.action == "adopted"
    assert "alembic_version" in inspect(create_engine(url)).get_table_names()
    assert len(_templates(url)) == 1  # existing data kept in place


def test_bootstrap_rebuilds_incompatible_keeping_templates(tmp_path):
    url = _url(tmp_path)
    engine = create_engine(url)
    # email_template + a superfluous table, missing the rest -> incompatible schema
    with engine.begin() as c:
        c.execute(
            text(
                "CREATE TABLE email_template (id INTEGER PRIMARY KEY, template_key VARCHAR, "
                "subject VARCHAR, body TEXT, updated_by VARCHAR, updated_at DATETIME)"
            )
        )
        c.execute(
            text(
                "INSERT INTO email_template (template_key, subject, body) "
                "VALUES ('scout_request', 'keep me', 'body')"
            )
        )
        c.execute(text("CREATE TABLE junk (id INTEGER PRIMARY KEY)"))

    r = bootstrap(url)
    assert r.action == "rebuilt"
    assert r.preserved["email_template"] == 1

    names = set(inspect(create_engine(url)).get_table_names())
    assert "junk" not in names  # superfluous nuked
    assert "cohort_target" in names  # rebuilt to the current schema
    rows = _templates(url)
    assert len(rows) == 1 and rows[0].subject == "keep me"  # template preserved


def test_bootstrap_migration_clears_uppflyttning_keeps_templates(tmp_path):
    from alembic import command

    from karverktyg.db.bootstrap import _alembic_cfg

    url = _url(tmp_path)
    engine = create_engine(url)
    # Managed DB one revision behind head (0001, before cohort_target exists).
    command.upgrade(_alembic_cfg(url), "0001")
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO email_template (template_key, subject, body) "
                "VALUES ('scout_request', 'keep me', 'body')"
            )
        )
        c.execute(
            text(
                "INSERT INTO uppflyttning_entry (cohort_year, member_no, source_avdelning, status) "
                "VALUES (2026, 1000, 'Spårare', 'ready')"
            )
        )

    r = bootstrap(url)
    assert r.action == "upgraded"
    assert "uppflyttning cleared" in r.detail

    with engine.connect() as c:
        # uppflyttning scratch gone, meaningful data kept
        assert c.execute(text("SELECT COUNT(*) FROM uppflyttning_entry")).scalar() == 0
        assert c.execute(text("SELECT COUNT(*) FROM email_template")).scalar() == 1
