from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select

from karverktyg.db import Base, FindingAck, make_sessionmaker
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
