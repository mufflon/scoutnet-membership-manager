"""
Post-hoc reconciliation (§7 Phase 1, reused by Phase 2).

After the operator has entered the moves manually, re-fetch the memberlist and
diff it against the changelist *intent*. Reports how many applied, which members
were not found, and which ended up somewhere other than intended. Compared
against intent, never against "the target should contain exactly the moved
cohort" — pre-existing members of a target are not drift (§17).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from karverktyg.scoutnet.models import MemberList
from karverktyg.uppflyttning.models import MasterSet


@dataclass
class ReconItem:
    """ReconItem."""

    member_no: str
    member_name: str
    intended_target: str | None
    intended_troop_id: int | None
    actual_avdelning: str | None = None
    actual_troop_id: int | None = None


@dataclass
class ReconResult:
    """ReconResult."""

    applied: list[ReconItem] = field(default_factory=list)
    not_found: list[ReconItem] = field(default_factory=list)
    elsewhere: list[ReconItem] = field(default_factory=list)

    @property
    def all_applied(self) -> bool:
        """All applied."""
        return not self.not_found and not self.elsewhere

    def summary(self) -> dict[str, int]:
        """Summary."""
        return {
            "applied": len(self.applied),
            "not_found": len(self.not_found),
            "elsewhere": len(self.elsewhere),
        }


def reconcile(master: MasterSet, memberlist_after: MemberList) -> ReconResult:
    """Reconcile."""
    by_no = memberlist_after.by_member_no()
    result = ReconResult()
    for e in master.ready():  # only the intended moves; overrides already applied
        after = by_no.get(e.member_no)
        item = ReconItem(
            member_no=e.member_no,
            member_name=after.full_name if after else e.member_name,
            intended_target=e.target_avdelning,
            intended_troop_id=e.target_troop_id,
        )
        if after is None:
            result.not_found.append(item)
            continue
        item.actual_avdelning = after.unit
        item.actual_troop_id = after.unit_troop_id
        if after.unit_troop_id == e.target_troop_id:
            result.applied.append(item)
        else:
            result.elsewhere.append(item)
    return result
