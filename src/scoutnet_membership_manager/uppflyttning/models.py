"""Uppflyttning master-set models (§17)."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from scoutnet_membership_manager.config.models import TransitionKind


class MoveStatus(enum.StrEnum):
    """MoveStatus."""

    READY = "ready"  # target resolved; the move can be exported/executed
    PENDING_TARGET = "pending_target"  # new_cohort_avdelning target not yet elected
    OFF_COHORT = "off_cohort"  # birth year off the bracket; manual, excluded
    EXCLUDED = "excluded"  # role-holder / adult; surfaced for review, not moved
    OVERRIDE_STAY = "override_stay"  # operator override: keep in place this year


@dataclass
class ElectedTarget:
    """Operator's cohort-level target election for a new_cohort_avdelning move (§17)."""

    avdelning: str
    troop_id: int | None = None


@dataclass
class MoveEntry:
    """MoveEntry."""

    member_no: str
    member_name: str  # live display only; never persisted (§9)
    birth_year: int | None
    source_avdelning: str | None
    source_troop_id: int | None
    target_avdelning: str | None
    target_troop_id: int | None
    transition: TransitionKind
    status: MoveStatus
    # Classified off-cohort (wrong age for the bracket). A **stable** marker: it
    # stays true even after a manual target override turns the row into a READY
    # move, so the member remains in the "misplaced" group rather than jumping into
    # an age transition (§7 Deferred architecture A).
    off_cohort: bool = False
    note: str = ""
    # The computed default target (before any override), so the UI can mark it.
    default_target: str | None = None
    # Per-member override (§17). "stay a year" is an expiry cohort year, not a
    # boolean, so it lapses by itself.
    override_target: str | None = None
    override_stay_until: int | None = None
    override_by: str | None = None
    # Operator has reviewed/handled this row (e.g. an off-cohort member left as-is
    # after checking with the other leaders). Advisory — removes it from the
    # "needs attention" set without moving anyone.
    acknowledged: bool = False

    @property
    def is_override(self) -> bool:
        """Is override."""
        return self.override_target is not None or self.override_stay_until is not None


@dataclass
class MasterSet:
    """MasterSet."""

    cohort_year: int
    entries: list[MoveEntry] = field(default_factory=list)

    def ready(self) -> list[MoveEntry]:
        """Ready."""
        return [e for e in self.entries if e.status is MoveStatus.READY]

    def pending(self) -> list[MoveEntry]:
        """Pending."""
        return [e for e in self.entries if e.status is MoveStatus.PENDING_TARGET]

    def off_cohort(self) -> list[MoveEntry]:
        """Off cohort."""
        return [e for e in self.entries if e.status is MoveStatus.OFF_COHORT]

    def excluded(self) -> list[MoveEntry]:
        """Excluded."""
        return [e for e in self.entries if e.status is MoveStatus.EXCLUDED]

    def kept(self) -> list[MoveEntry]:
        """Members the operator chose to keep in place (override_stay)."""
        return [e for e in self.entries if e.status is MoveStatus.OVERRIDE_STAY]

    def by_target(self) -> dict[str, list[MoveEntry]]:
        """By target."""
        out: dict[str, list[MoveEntry]] = {}
        for e in self.ready():
            out.setdefault(e.target_avdelning or "", []).append(e)
        return out
