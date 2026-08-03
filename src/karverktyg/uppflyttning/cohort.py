"""Cohort year N: derivation from the live term and the config cross-check (§17).

N is the calendar year of the autumn term. A scouting year is Höst N + Vår N+1,
so a "Vår YYYY" label implies N = YYYY − 1. The guard refuses to compute when a
configured N disagrees with the live term — the cheapest guard against the most
damaging silent error in the tool.
"""

from __future__ import annotations


class CohortYearConflict(RuntimeError):
    """Configured cohort year N and the live term disagree, or N is unknown."""


def derive_n_from_term_label(current_term_label: str | None) -> int | None:
    """`"Höst YYYY"` -> YYYY, `"Vår YYYY"` -> YYYY − 1. None if undeterminable."""
    if not current_term_label:
        return None
    year: int | None = None
    season: str | None = None
    for token in current_term_label.replace("-", " ").split():
        if len(token) == 4 and token.isdigit():
            year = int(token)
        low = token.casefold()
        if low.startswith(("höst", "host")):
            season = "autumn"
        elif low.startswith(("vår", "var")):
            season = "spring"
    if year is None or season is None:
        return None
    return year if season == "autumn" else year - 1


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
