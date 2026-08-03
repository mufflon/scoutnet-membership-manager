"""Uppflyttning master-set models (§17)."""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from karverktyg.config.models import TransitionKind


class MoveStatus(enum.StrEnum):
    READY = "ready"  # target resolved; the move can be exported/executed
    PENDING_TARGET = "pending_target"  # new_cohort_avdelning target not yet elected
    OFF_COHORT = "off_cohort"  # birth year off the bracket; manual, excluded
    EXCLUDED = "excluded"  # role-holder / adult; surfaced for review, not moved


@dataclass
class MoveEntry:
    member_no: str
    member_name: str  # live display only; never persisted (§9)
    birth_year: int | None
    source_avdelning: str | None
    source_troop_id: int | None
    target_avdelning: str | None
    target_troop_id: int | None
    transition: TransitionKind
    status: MoveStatus
    note: str = ""
    # Per-member override (§17). "stay a year" is an expiry cohort year, not a
    # boolean, so it lapses by itself.
    override_target: str | None = None
    override_stay_until: int | None = None
    override_by: str | None = None

    @property
    def is_override(self) -> bool:
        return self.override_target is not None or self.override_stay_until is not None


@dataclass
class MasterSet:
    cohort_year: int
    entries: list[MoveEntry] = field(default_factory=list)

    def ready(self) -> list[MoveEntry]:
        return [e for e in self.entries if e.status is MoveStatus.READY]

    def pending(self) -> list[MoveEntry]:
        return [e for e in self.entries if e.status is MoveStatus.PENDING_TARGET]

    def off_cohort(self) -> list[MoveEntry]:
        return [e for e in self.entries if e.status is MoveStatus.OFF_COHORT]

    def excluded(self) -> list[MoveEntry]:
        return [e for e in self.entries if e.status is MoveStatus.EXCLUDED]

    def by_target(self) -> dict[str, list[MoveEntry]]:
        out: dict[str, list[MoveEntry]] = {}
        for e in self.ready():
            out.setdefault(e.target_avdelning or "", []).append(e)
        return out
