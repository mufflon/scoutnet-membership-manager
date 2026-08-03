"""Per-member overrides layered on the computed master set (§17).

Overrides survive recomputation: recompute the set, then re-apply the stored
overrides. "Stay a year" is an expiry cohort year, so it lapses by itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from karverktyg.roster import TroopIndex
from karverktyg.uppflyttning.models import MasterSet, MoveStatus


@dataclass
class Override:
    member_no: str
    target_avdelning: str | None = None
    stay_until: int | None = None  # keep in the current avdelning through this cohort year
    by: str | None = None


def apply_overrides(master: MasterSet, overrides: list[Override], index: TroopIndex) -> MasterSet:
    by_member = {o.member_no: o for o in overrides}
    for e in master.entries:
        o = by_member.get(e.member_no)
        if o is None:
            continue
        e.override_by = o.by
        # A stay override that has not yet lapsed keeps the member in place.
        if o.stay_until is not None and o.stay_until >= master.cohort_year:
            e.override_stay_until = o.stay_until
            e.status = MoveStatus.OVERRIDE_STAY
            e.note = (f"override by {o.by}: stay in {e.source_avdelning} through "
                      f"cohort {o.stay_until}")
            continue
        if o.target_avdelning:
            e.override_target = o.target_avdelning
            e.target_avdelning = o.target_avdelning
            e.target_troop_id = index.name_to_id.get(o.target_avdelning)
            e.status = MoveStatus.READY if e.target_troop_id else MoveStatus.PENDING_TARGET
            e.note = f"override target set by {o.by}"
    return master
