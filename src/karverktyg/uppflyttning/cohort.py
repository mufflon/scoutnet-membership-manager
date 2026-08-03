"""
Cohort year N: derivation from the live term and the config cross-check (§17).

N is the calendar year of the autumn term the scouts are being moved INTO. The
uppflyttning is always computed before the summer camp, so N = the year in the
current_term label for BOTH seasons — "Höst YYYY" and "Vår YYYY" both give
N = YYYY:

* In spring ("Vår YYYY") you are planning the coming summer's move into Höst
  YYYY, while the members are still placed for the prior scout year.
* In late summer / early autumn ("Höst YYYY", pre-move) you are completing that
  same move just before (or just after) the term rolls.

Both read the same N. Deriving N as YYYY-1 in spring — naming the *current*
scout year rather than the autumn the move feeds — is exactly the bug that makes
the master set empty in spring, since every mover looks correctly placed.

The guard refuses to compute when a configured N disagrees with the live term —
the cheapest guard against the most damaging silent error in the tool.
"""

from __future__ import annotations


class CohortYearConflict(RuntimeError):
    """Configured cohort year N and the live term disagree, or N is unknown."""


def derive_n_from_term_label(current_term_label: str | None) -> int | None:
    """
    N = the 4-digit year in the term label, for both "Höst" and "Vår" (the
    autumn cohort the coming move feeds). Requires a recognisable term label;
    returns None otherwise.
    """
    if not current_term_label:
        return None
    year: int | None = None
    has_season = False
    for token in current_term_label.replace("-", " ").split():
        if len(token) == 4 and token.isdigit():  # noqa: PLR2004 - 4-digit year
            year = int(token)
        if token.casefold().startswith(("höst", "host", "vår", "var")):
            has_season = True
    if year is None or not has_season:
        return None
    return year


def resolve_cohort_year(config_n: int | None, current_term_label: str | None) -> int:
    """Return the effective cohort year N, guarded against the live term (§17)."""
    derived = derive_n_from_term_label(current_term_label)
    if config_n is None:
        if derived is None:
            raise CohortYearConflict(
                "cohort year N is not configured and cannot be derived from the "
                f"live term label {current_term_label!r}; set cohort_year in config"
            )
        return derived
    if derived is not None and derived != config_n:
        raise CohortYearConflict(
            f"configured cohort year N={config_n} disagrees with the live term "
            f"{current_term_label!r} (implies N={derived}); refusing to compute a "
            "master set until they agree"
        )
    return config_n
