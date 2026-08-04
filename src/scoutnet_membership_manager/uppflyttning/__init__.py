"""
Uppflyttning engine (CLAUDE.md §17).

Pure computation over a memberlist and the kår config: members + config -> a
master set of moves, each with a transition kind, a resolved or pending target,
and off-cohort / excluded flags. Cohort is keyed on birth year, never school
year, and the cohort year N is guarded against the live term (§17).
"""

from scoutnet_membership_manager.uppflyttning.cohort import CohortYearConflict, resolve_cohort_year
from scoutnet_membership_manager.uppflyttning.decisions import (
    clear_all_decisions,
    clear_decision,
    get_decisions,
    upsert_decision,
)
from scoutnet_membership_manager.uppflyttning.engine import (
    MISPLACED_GROUP,
    compute_master_set,
    scope_master_set,
)
from scoutnet_membership_manager.uppflyttning.models import (
    ElectedTarget,
    MasterSet,
    MoveEntry,
    MoveStatus,
)
from scoutnet_membership_manager.uppflyttning.overrides import Override, apply_overrides
from scoutnet_membership_manager.uppflyttning.targets import (
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
