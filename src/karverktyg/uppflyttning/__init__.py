"""
Uppflyttning engine (CLAUDE.md §17).

Pure computation over a memberlist and the kår config: members + config -> a
master set of moves, each with a transition kind, a resolved or pending target,
and off-cohort / excluded flags. Cohort is keyed on birth year, never school
year, and the cohort year N is guarded against the live term (§17).
"""

from karverktyg.uppflyttning.cohort import CohortYearConflict, resolve_cohort_year
from karverktyg.uppflyttning.engine import compute_master_set
from karverktyg.uppflyttning.models import MasterSet, MoveEntry, MoveStatus

__all__ = [
    "CohortYearConflict",
    "MasterSet",
    "MoveEntry",
    "MoveStatus",
    "compute_master_set",
    "resolve_cohort_year",
]
