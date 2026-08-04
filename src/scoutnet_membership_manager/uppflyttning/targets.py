"""
Persisted cohort-target elections (§17).

Which avdelning a new_cohort_avdelning cohort moves into is elected once, in-app,
and stored so the pending moves resolve and the changelist can be exported.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from scoutnet_membership_manager.config.models import Bracket
from scoutnet_membership_manager.db.models import CohortTarget
from scoutnet_membership_manager.uppflyttning.models import ElectedTarget


def get_elected_target(
    session: Session, cohort_year: int, bracket: Bracket
) -> ElectedTarget | None:
    """The elected target for a cohort/bracket, or None if not yet elected."""
    row = session.execute(
        select(CohortTarget).where(
            CohortTarget.cohort_year == cohort_year,
            CohortTarget.bracket == str(bracket),
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return ElectedTarget(avdelning=row.target_avdelning, troop_id=row.target_troop_id)


def set_elected_target(
    session: Session,
    cohort_year: int,
    bracket: Bracket,
    avdelning: str,
    troop_id: int | None,
    by: str | None = None,
) -> None:
    """Elect (or re-elect) the target avdelning for a cohort/bracket."""
    row = session.execute(
        select(CohortTarget).where(
            CohortTarget.cohort_year == cohort_year,
            CohortTarget.bracket == str(bracket),
        )
    ).scalar_one_or_none()
    if row is not None:
        row.target_avdelning, row.target_troop_id, row.elected_by = avdelning, troop_id, by
    else:
        session.add(
            CohortTarget(
                cohort_year=cohort_year,
                bracket=str(bracket),
                target_avdelning=avdelning,
                target_troop_id=troop_id,
                elected_by=by,
            )
        )
    session.flush()


def clear_elected_target(session: Session, cohort_year: int, bracket: Bracket) -> None:
    """Remove a cohort/bracket election (moves revert to pending)."""
    row = session.execute(
        select(CohortTarget).where(
            CohortTarget.cohort_year == cohort_year,
            CohortTarget.bracket == str(bracket),
        )
    ).scalar_one_or_none()
    if row is not None:
        session.delete(row)
        session.flush()
