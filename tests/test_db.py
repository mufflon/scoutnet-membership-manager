from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select

from karverktyg.db import (
    Base,
    FindingAck,
    UppflyttningEntry,
    WriteJournal,
    WriteRun,
    make_sessionmaker,
)
from karverktyg.db.bootstrap import _MEANINGFUL, _UPPFLYTTNING_TABLES, _clear_uppflyttning
from karverktyg.db.session import get_session

ROOT = Path(__file__).resolve().parent.parent

# Personal-data substrings that must never appear in a column name or a
# migration (§9). A cheap heuristic, not a guarantee.
FORBIDDEN = (
    "name",
    "email",
    "phone",
    "mobile",
    "address",
    "postcode",
    "town",
    "ssno",
    "personnummer",
    "birth",
    "dob",
)


def test_no_personal_data_columns_in_models():
    for table in Base.metadata.tables.values():
        for col in table.columns:
            lowered = col.name.lower()
            assert not any(bad in lowered for bad in FORBIDDEN), (
                f"personal-data-like column {table.name}.{col.name}"
            )


def test_no_personal_data_columns_in_migrations():
    for mig in (ROOT / "migrations" / "versions").glob("*.py"):
        text = mig.read_text("utf-8").lower()
        for line in text.splitlines():
            if "sa.column(" not in line:
                continue
            assert not any(bad in line for bad in FORBIDDEN), (
                f"personal-data-like column in {mig.name}: {line.strip()}"
            )


def test_ack_roundtrip():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = make_sessionmaker(engine)
    with get_session(factory) as s:
        s.add(FindingAck(member_no="100", finding_type="bad_phone", value_hash="abc"))
    with get_session(factory) as s:
        rows = s.execute(select(FindingAck)).scalars().all()
    assert len(rows) == 1
    assert rows[0].member_no == "100"


def test_write_journal_roundtrip():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = make_sessionmaker(engine)
    with get_session(factory) as s:
        s.add(WriteRun(id="run-1", kind="uppflyttning", cohort_year=2026, mode="dry_run"))
        s.add(
            WriteJournal(
                run_id="run-1",
                chunk_id=0,
                member_no="1000",
                intended_status="confirmed",
                intended_troop_id=12345,
                source_troop_id=11111,
            )
        )
    with get_session(factory) as s:
        run = s.execute(select(WriteRun)).scalars().one()
        entry = s.execute(select(WriteJournal)).scalars().one()
    assert run.state == "pending"  # lifecycle default
    assert entry.member_no == "1000"
    assert (entry.state, entry.attempts) == ("pending", 0)


def test_clear_uppflyttning_spares_write_tables():
    # Resume-after-crash depends on the journal surviving a migration; the
    # scratch-clear must touch uppflyttning_entry only, never the write tables (§8).
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = make_sessionmaker(engine)
    with get_session(factory) as s:
        s.add(UppflyttningEntry(cohort_year=2026, member_no="1000", status="ready"))
        s.add(WriteRun(id="run-1", kind="uppflyttning", mode="execute", state="running"))
        s.add(
            WriteJournal(
                run_id="run-1",
                chunk_id=0,
                member_no="1000",
                intended_status="confirmed",
                intended_troop_id=12345,
            )
        )

    _clear_uppflyttning(engine)

    with get_session(factory) as s:
        assert s.execute(select(UppflyttningEntry)).scalars().all() == []  # scratch gone
        assert len(s.execute(select(WriteRun)).scalars().all()) == 1  # run kept
        assert len(s.execute(select(WriteJournal)).scalars().all()) == 1  # journal kept


def test_write_tables_are_meaningful_not_scratch():
    for table in ("write_run", "write_journal", "snapshot"):
        assert table in _MEANINGFUL, f"{table} must be preserved on rebuild, not lost"
        assert table not in _UPPFLYTTNING_TABLES, f"{table} must not be wiped as scratch"
