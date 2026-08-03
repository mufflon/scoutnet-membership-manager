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
