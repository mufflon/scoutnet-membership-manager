"""
Uppflyttning engine (CLAUDE.md §17).

Pure computation over a memberlist and the kår config: members + config -> a
master set of moves, each with a transition kind, a resolved or pending target,
and off-cohort / excluded flags. Cohort is keyed on birth year, never school
year, and the cohort year N is guarded against the live term (§17).
"""

from karverktyg.uppflyttning.cohort import CohortYearConflict, resolve_cohort_year
from karverktyg.uppflyttning.decisions import (
    clear_all_decisions,
    clear_decision,
    get_decisions,
    upsert_decision,
)
from karverktyg.uppflyttning.engine import (
    MISPLACED_GROUP,
    compute_master_set,
    scope_master_set,
)
from karverktyg.uppflyttning.models import ElectedTarget, MasterSet, MoveEntry, MoveStatus
from karverktyg.uppflyttning.overrides import Override, apply_overrides
from karverktyg.uppflyttning.targets import (
    clear_elected_target,
    get_elected_target,
    set_elected_target,
)

__all__ = [
    "MISPLACED_GROUP",
    "CohortYearConflict",
    "ElectedTarget",
    "MasterSet",
    "MoveEntry",
    "MoveStatus",
    "Override",
    "apply_overrides",
    "clear_all_decisions",
    "clear_decision",
    "clear_elected_target",
    "compute_master_set",
    "get_decisions",
    "get_elected_target",
    "resolve_cohort_year",
    "scope_master_set",
    "set_elected_target",
    "upsert_decision",
]
