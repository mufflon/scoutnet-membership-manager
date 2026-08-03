"""
Typed configuration models (§17).

The engine understands the four transition kinds and reads everything else from
config. Cohort is keyed on **birth year**, never school year (§17); ages here
are *cohort ages* = N − birth_year.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field, model_validator


class Bracket(enum.StrEnum):
    """Scout age brackets, keyed to Scoutnet unit_type."""

    SPARARE = "sparare"
    UPPTACKARE = "upptackare"
    AVENTYRARE = "aventyrare"
    UTMANARE = "utmanare"
    ROVER = "rover"
    ANNAT = "annat"


# Scoutnet unit_type raw_value codes observed in the capture (§4).
_UNIT_TYPE_CODE: dict[Bracket, int] = {
    Bracket.SPARARE: 2,
    Bracket.UPPTACKARE: 3,
    Bracket.AVENTYRARE: 4,
    Bracket.UTMANARE: 5,
    Bracket.ROVER: 6,
    Bracket.ANNAT: 7,
}
_CODE_TO_BRACKET: dict[int, Bracket] = {v: k for k, v in _UNIT_TYPE_CODE.items()}


def unit_type_code(bracket: Bracket) -> int:
    """The Scoutnet unit_type code for a bracket."""
    return _UNIT_TYPE_CODE[bracket]


def bracket_by_unit_type_code(code: int | str | None) -> Bracket | None:
    """The bracket for a Scoutnet unit_type code, or None if unrecognised."""
    if code is None:
        return None
    try:
        numeric = int(code)
    except (TypeError, ValueError):
        return None
    return _CODE_TO_BRACKET.get(numeric)


class TransitionKind(enum.StrEnum):
    """How a bracket's oldest cohort moves up at the summer shift (§17)."""

    SAME_WEEKDAY = "same_weekday"  # Spårare → Upptäckare (matched weekday)
    MERGE = "merge"  # Upptäckare → one Äventyrare avdelning
    NEW_COHORT_AVDELNING = "new_cohort_avdelning"  # Äventyrare → new Utmanare
    NEVER_AUTO = "never_auto"  # Utmanare, Rover
    NONE = "none"  # Annat / Ledare — not a scout bracket


class BracketRule(BaseModel):
    """Age span and transition kind for one bracket."""

    bracket: Bracket
    # Cohort-age span (N − birth_year). None for brackets that are not
    # age-bounded (Rover, Annat).
    age_min: int | None = None
    age_max: int | None = None
    transition: TransitionKind
    # Whether the §11 age / multi-avdelning structural checks apply.
    structural_checks: bool = True
    # §20 KPI thresholds, per åldersgrupp — younger avdelningar need denser
    # staffing. These only *flag*, never hard-limit. None => no flag for this
    # bracket. scouts_per_leader_max is scouts-per-one-leader (e.g. 6.0 => 6:1).
    scouts_per_leader_max: float | None = None
    projected_size_max: int | None = None


class Avdelning(BaseModel):
    """
    One avdelning's config: its existence and attributes (bracket, weekday, move
    target, cohort_year) — **never a troop_id**. The id is resolved live from
    ``unit.raw_value``; for a brand-new avdelning too empty to appear in the
    memberlist, the operator supplies the id at the target election, stored as run
    metadata keyed to the cohort year (§17), not here. A config that carried the id
    would go stale and offer itself as a plausible wrong-cohort default next year.
    """

    name: str
    bracket: Bracket
    # 0 = Monday .. 6 = Sunday. Required for same_weekday sources/targets.
    weekday: int | None = Field(default=None, ge=0, le=6)
    # Default move target avdelning name (same_weekday / merge). Not set for
    # new_cohort_avdelning (resolved by cohort_year) or never_auto.
    default_target: str | None = None
    # The birth year an Utmanare avdelning was built around (§17). Describes the
    # core, never used to move or flag anyone.
    cohort_year: int | None = None
    is_18plus: bool = False


class ExpectedPost(BaseModel):
    """
    An expected förtroendeuppdrag, for the opt-in vacancy view (§18).

    Strictly opt-in: with no expected posts configured, no vacancies are
    reported and an unfilled post is never treated as an error.
    """

    role_key: str
    count: int = Field(default=1, ge=1)
    # Optional display label for a vacancy row; falls back to the role_key,
    # since an unfilled post has no holder to read a role_name from.
    label: str | None = None


class KarConfig(BaseModel):
    """The whole kår configuration: brackets and avdelningar (§13, §17)."""

    name: str
    group_id: str
    # Cohort year N. None => derive from the live term, guarded by the
    # cross-check in uppflyttning.cohort (§17).
    cohort_year_n: int | None = None
    # Marks a shipped placeholder configuration (§13).
    placeholder: bool = True
    brackets: list[BracketRule]
    avdelningar: list[Avdelning]

    # --- Förtroendeuppdrag (§18) -------------------------------------------
    # The blade's three sections (board / other / delegate) and their order are
    # hard-coded in karverktyg.fortroende — uniform for this kår; another kår
    # would extend those lists. Config here only carries kår-specific data:
    # optional role_key -> display label override (rare, ships empty), and the
    # opt-in årsmöte vacancy list.
    role_label_overrides: dict[str, str] = Field(default_factory=dict)
    # Optional expected posts for the årsmöte vacancy view (§18). Opt-in.
    expected_fortroende: list[ExpectedPost] = Field(default_factory=list)

    # --- Validation --------------------------------------------------------
    @model_validator(mode="after")
    def _validate(self) -> KarConfig:
        rule_by_bracket = {r.bracket: r for r in self.brackets}
        if len(rule_by_bracket) != len(self.brackets):
            raise ValueError("duplicate bracket in 'brackets'")

        names = [a.name for a in self.avdelningar]
        if len(set(names)) != len(names):
            raise ValueError("duplicate avdelning name")
        name_set = set(names)

        for a in self.avdelningar:
            if a.bracket not in rule_by_bracket:
                raise ValueError(f"avdelning {a.name!r} references unknown bracket {a.bracket}")
            rule = rule_by_bracket[a.bracket]
            if rule.transition is TransitionKind.SAME_WEEKDAY and a.weekday is None:
                raise ValueError(f"same_weekday avdelning {a.name!r} needs a weekday")
            if a.default_target is not None and a.default_target not in name_set:
                raise ValueError(
                    f"avdelning {a.name!r} default_target {a.default_target!r} does not exist"
                )

        # cohort_year must be unique among avdelningar that set it, so
        # "the Utmanare avdelning whose cohort_year is N" resolves unambiguously.
        seen: dict[int, str] = {}
        for a in self.avdelningar:
            if a.cohort_year is None:
                continue
            if a.cohort_year in seen:
                raise ValueError(
                    f"cohort_year {a.cohort_year} is shared by {seen[a.cohort_year]!r} "
                    f"and {a.name!r}; it must be unique so a move target resolves"
                )
            seen[a.cohort_year] = a.name
        return self

    # --- Lookups -----------------------------------------------------------
    def rule(self, bracket: Bracket) -> BracketRule:
        """The rule for a bracket; raises KeyError if not configured."""
        for r in self.brackets:
            if r.bracket is bracket:
                return r
        raise KeyError(bracket)

    def avdelning(self, name: str) -> Avdelning | None:
        """The avdelning with this name, or None."""
        for a in self.avdelningar:
            if a.name == name:
                return a
        return None

    def avdelningar_in(self, bracket: Bracket) -> list[Avdelning]:
        """All avdelningar in a bracket."""
        return [a for a in self.avdelningar if a.bracket is bracket]

    def target_for_cohort(self, bracket: Bracket, cohort_year: int) -> Avdelning | None:
        """
        Return the avdelning of ``bracket`` whose cohort_year matches — the
        new_cohort_avdelning target for that cohort (§17).
        """
        for a in self.avdelningar_in(bracket):
            if a.cohort_year == cohort_year:
                return a
        return None

    def eighteen_plus_avdelningar(self) -> list[str]:
        """Names of avdelningar configured as 18+ (e.g. Ledare)."""
        return [a.name for a in self.avdelningar if a.is_18plus]
