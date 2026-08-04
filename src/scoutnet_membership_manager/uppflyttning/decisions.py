"""
Persisted per-member uppflyttning decisions (§9, §17).

Stored in ``uppflyttning_entry`` keyed on (cohort_year, member_no): a target
override, a "stay a year" expiry, and/or an acknowledged/handled flag. Only the
decision is stored — names and the computed move are re-derived live and the
decisions re-applied, so they survive recomputation.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from scoutnet_membership_manager.db.models import UppflyttningEntry
from scoutnet_membership_manager.uppflyttning.overrides import Override

_DECISION = "decision"  # status marker for a stored decision row


def get_decisions(session: Session, cohort_year: int) -> list[Override]:
    """All stored per-member decisions for a cohort year."""
    rows = session.execute(
        select(UppflyttningEntry).where(UppflyttningEntry.cohort_year == cohort_year)
    ).scalars()
    return [
        Override(
            member_no=r.member_no,
            target_avdelning=r.override_target,
            stay_until=r.override_stay_until,
            acknowledged=r.approved,
            by=r.override_by,
        )
        for r in rows
    ]


def _row(session: Session, cohort_year: int, member_no: str) -> UppflyttningEntry | None:
    return session.execute(
        select(UppflyttningEntry).where(
            UppflyttningEntry.cohort_year == cohort_year,
            UppflyttningEntry.member_no == member_no,
        )
    ).scalar_one_or_none()


def upsert_decision(
    session: Session,
    cohort_year: int,
    member_no: str,
    *,
    target_avdelning: str | None = None,
    stay_until: int | None = None,
    acknowledged: bool | None = None,
    by: str | None = None,
) -> None:
    """
    Create or update a member's decision. Only provided fields change; pass
    ``target_avdelning=""`` to clear a target override.
    """
    row = _row(session, cohort_year, member_no)
    if row is None:
        row = UppflyttningEntry(cohort_year=cohort_year, member_no=member_no, status=_DECISION)
        session.add(row)
    if target_avdelning is not None:
        row.override_target = target_avdelning or None
    if stay_until is not None:
        row.override_stay_until = stay_until or None
    if acknowledged is not None:
        row.approved = acknowledged
    if by is not None:
        row.override_by = by
    session.flush()


def clear_decision(session: Session, cohort_year: int, member_no: str) -> None:
    """Remove a member's stored decision entirely."""
    row = _row(session, cohort_year, member_no)
    if row is not None:
        session.delete(row)
        session.flush()


def clear_all_decisions(session: Session, cohort_year: int) -> int:
    """Remove every stored per-member decision for a cohort year. Returns count."""
    result = session.execute(
        delete(UppflyttningEntry).where(UppflyttningEntry.cohort_year == cohort_year)
    )
    session.flush()
    return result.rowcount or 0
