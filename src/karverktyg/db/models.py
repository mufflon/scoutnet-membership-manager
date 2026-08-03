"""
ORM models (§9). Deliberately no personal-data columns.

Persisted state is workflow only, keyed on ``member_no``. Personal data (names,
addresses, personnummer, email, phone) and even birth year are never stored —
they are fetched live and joined at render time.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


class UppflyttningEntry(Base):
    """
    One member's place in a computed master set, with override and approval
    (§9). Source/target are avdelningar + troop_ids, never anything personal.
    """

    __tablename__ = "uppflyttning_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cohort_year: Mapped[int] = mapped_column(Integer, index=True)
    member_no: Mapped[str] = mapped_column(String(32), index=True)
    source_avdelning: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_troop_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_avdelning: Mapped[str | None] = mapped_column(String(64), nullable=True)
    target_troop_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32))
    # Per-member override (§17). "stay a year" is an expiry cohort year.
    override_target: Mapped[str | None] = mapped_column(String(64), nullable=True)
    override_stay_until: Mapped[int | None] = mapped_column(Integer, nullable=True)
    override_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FindingAck(Base):
    """
    Acknowledgement of a finding, keyed to a hash of the offending value so it
    re-surfaces if the value changes (§11). Not personal data.
    """

    __tablename__ = "finding_ack"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_no: Mapped[str] = mapped_column(String(32), index=True)
    finding_type: Mapped[str] = mapped_column(String(48))
    value_hash: Mapped[str] = mapped_column(String(32))
    acknowledged_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MessageLog(Base):
    """Idempotency log for mail (§9, §10): who was sent what, when. No address."""

    __tablename__ = "message_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_no: Mapped[str] = mapped_column(String(32), index=True)
    message_type: Mapped[str] = mapped_column(String(48))
    sent_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CohortTarget(Base):
    """
    Operator's cohort-level target election for a new_cohort_avdelning move
    (§17): which avdelning the Äventyrare cohort of a given year moves into.
    Elected once for the whole cohort. Not personal data.
    """

    __tablename__ = "cohort_target"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cohort_year: Mapped[int] = mapped_column(Integer, index=True)
    bracket: Mapped[str] = mapped_column(String(32))
    target_avdelning: Mapped[str] = mapped_column(String(64))
    target_troop_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elected_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    elected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    __table_args__ = (UniqueConstraint("cohort_year", "bracket", name="uq_cohort_target"),)


class WriteRun(Base):
    """
    One operator-initiated bulk write run (§8): an uppflyttning apply, an undo,
    or a decommission. Progress is server-side state polled by the frontend, so
    the run survives the tab closing; the journal below lets it survive a
    restart. Keyed on ``member_no`` in its journal rows — no personal data.
    """

    __tablename__ = "write_run"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # uuid4 hex-with-dashes
    kind: Mapped[str] = mapped_column(String(32))  # uppflyttning | undo | decommission
    cohort_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Set when kind == "undo": the run this one reverses. Logical link (like
    # member_no elsewhere), not a DB foreign key, matching the rest of the schema.
    parent_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    mode: Mapped[str] = mapped_column(String(16))  # dry_run | execute (dry-run default, §8)
    # pending -> running -> done | failed | aborted
    state: Mapped[str] = mapped_column(String(16), default="pending")
    snapshot_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class WriteJournal(Base):
    """
    One intended per-member operation in a run (§8, "journal first"): persisted
    before the first request, then moved pending -> in_flight -> done | failed.
    ``source_troop_id`` records the observed prior state so an undo can be
    computed from what was, never from the intended change. No personal data.
    """

    __tablename__ = "write_journal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[str] = mapped_column(String(36), index=True)  # logical link to write_run.id
    chunk_id: Mapped[int] = mapped_column(Integer)  # monotonic within a run
    member_no: Mapped[str] = mapped_column(String(32), index=True)
    intended_status: Mapped[str] = mapped_column(String(16))  # "confirmed" for uppflyttning (§3)
    intended_troop_id: Mapped[int] = mapped_column(Integer)  # the only field a move changes
    source_troop_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # pending -> in_flight -> done | failed
    state: Mapped[str] = mapped_column(String(16), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)  # per-member 400 string / body


class Snapshot(Base):
    """
    Metadata for a full-memberlist snapshot taken before a bulk run (§8). The
    snapshot *file* — which does contain personal data, the one sanctioned
    exception — lives on a mounted volume, never in Postgres, git or an image.
    This row only records the file's existence for listing and undo; retention
    is time-based on ``taken_at``. No personal data in this row.
    """

    __tablename__ = "snapshot"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    path: Mapped[str] = mapped_column(String(512))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    taken_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EmailTemplate(Base):
    """
    Editable email template (§10). Overrides the shipped default for its key.
    Template text is content, not personal data.
    """

    __tablename__ = "email_template"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_key: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    subject: Mapped[str] = mapped_column(String(256))
    body: Mapped[str] = mapped_column(Text)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
