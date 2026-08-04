"""
Typed configuration models (§13, §17).

The national age-bracket ladder is fixed for every Swedish kår, so it lives in
**code** here (``BRACKETS``), never in a kår's config. A kår's config is only its
avdelningar — each with an optional meeting ``weekday`` and an optional explicit
move ``target`` — and nothing else: which bracket a member is in, troop ids and
the kår's group id are all read live from the member data. The config carries a
``version`` so older files can be migrated forward (see ``loader.migrate``), and
with **no config at all** the tool still runs: avdelningar are inferred from the
data and moves fall back to the universal routing rule.

Cohort is keyed on **birth year**, never school year (§17); ages here are cohort
ages = N − birth_year.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field, model_validator

CONFIG_VERSION = 1


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
    """
    The uppflyttning group a moving cohort belongs to — a UI/label key derived
    from the *source* bracket, not a per-kår setting. Routing itself is uniform
    (same-weekday → sole candidate → per-person, §17); these only name the groups.
    """

    SAME_WEEKDAY = "same_weekday"  # Spårare → Upptäckare
    MERGE = "merge"  # Upptäckare → Äventyrare
    NEW_COHORT_AVDELNING = "new_cohort_avdelning"  # Äventyrare → Utmanare
    NEVER_AUTO = "never_auto"  # Utmanare, Rover
    NONE = "none"  # Annat / Ledare — not a scout bracket


class BracketRule(BaseModel):
    """Age span and structural-check flag for one bracket (national, in code)."""

    bracket: Bracket
    # Cohort-age span (N − birth_year). None for brackets that are not
    # age-bounded (Rover, Annat).
    age_min: int | None = None
    age_max: int | None = None
    # Whether the §11 age / multi-avdelning structural checks apply.
    structural_checks: bool = True


# The national åldersgrupp ladder — identical for every Swedish kår (Utmanare tops
# out at 19 by national decision), so it is code, not config.
BRACKETS: list[BracketRule] = [
    BracketRule(bracket=Bracket.SPARARE, age_min=8, age_max=9),
    BracketRule(bracket=Bracket.UPPTACKARE, age_min=10, age_max=11),
    BracketRule(bracket=Bracket.AVENTYRARE, age_min=12, age_max=14),
    BracketRule(bracket=Bracket.UTMANARE, age_min=15, age_max=19, structural_checks=False),
    BracketRule(bracket=Bracket.ROVER, structural_checks=False),
    BracketRule(bracket=Bracket.ANNAT, structural_checks=False),
]
_BRACKET_RULE: dict[Bracket, BracketRule] = {b.bracket: b for b in BRACKETS}

# The group a moving cohort is shown under, by source bracket (labels only).
_TRANSITION_BY_BRACKET: dict[Bracket, TransitionKind] = {
    Bracket.SPARARE: TransitionKind.SAME_WEEKDAY,
    Bracket.UPPTACKARE: TransitionKind.MERGE,
    Bracket.AVENTYRARE: TransitionKind.NEW_COHORT_AVDELNING,
}


def transition_for(bracket: Bracket) -> TransitionKind:
    """The uppflyttning group key for a source bracket (a label, not behaviour)."""
    return _TRANSITION_BY_BRACKET.get(bracket, TransitionKind.NEVER_AUTO)


class Avdelning(BaseModel):
    """
    One avdelning's config: its meeting ``weekday`` and an optional explicit move
    ``target`` — **never a troop_id** (resolved live from ``unit.raw_value``) and
    never a bracket-specific transition. ``name`` and ``bracket`` may be declared
    here or left to be inferred from the member data; declaring them lets an empty
    or brand-new avdelning exist before anyone is in it.
    """

    name: str
    bracket: Bracket
    # 0 = Monday .. 6 = Sunday. Enables the same-weekday move hint.
    weekday: int | None = Field(default=None, ge=0, le=6)
    # Explicit move target avdelning name — the direct-target mode. Overrides the
    # weekday/sole-candidate rule for this source. Absent → universal rule (§17).
    target: str | None = None


class ExpectedPost(BaseModel):
    """
    An expected förtroendeuppdrag, for the opt-in vacancy view (§18).

    Strictly opt-in: with no expected posts configured, no vacancies are
    reported and an unfilled post is never treated as an error.
    """

    role_key: str
    count: int = Field(default=1, ge=1)
    label: str | None = None


class KarConfig(BaseModel):
    """
    A kår's configuration (§13): a version, an optional display name, and the
    avdelningar. Brackets are national (see ``BRACKETS``); the group id and every
    avdelning's bracket/troop_id are inferred from the data when not declared.
    """

    version: int = CONFIG_VERSION
    name: str | None = None
    avdelningar: list[Avdelning] = Field(default_factory=list)

    # --- Förtroendeuppdrag (§18) -------------------------------------------
    # Section classification is hard-coded in karverktyg.fortroende; config here
    # only carries an optional role_key -> label override (rare) and the opt-in
    # årsmöte vacancy list.
    role_label_overrides: dict[str, str] = Field(default_factory=dict)
    expected_fortroende: list[ExpectedPost] = Field(default_factory=list)

    # --- Validation --------------------------------------------------------
    @model_validator(mode="after")
    def _validate(self) -> KarConfig:
        names = [a.name for a in self.avdelningar]
        if len(set(names)) != len(names):
            raise ValueError("duplicate avdelning name")
        name_set = set(names)
        for a in self.avdelningar:
            if a.target is not None and a.target not in name_set:
                raise ValueError(f"avdelning {a.name!r} target {a.target!r} does not exist")
        return self

    # --- Lookups -----------------------------------------------------------
    def rule(self, bracket: Bracket) -> BracketRule:
        """The national rule for a bracket; raises KeyError if unknown."""
        return _BRACKET_RULE[bracket]

    def avdelning(self, name: str) -> Avdelning | None:
        """The declared avdelning with this name, or None."""
        for a in self.avdelningar:
            if a.name == name:
                return a
        return None

    def avdelningar_in(self, bracket: Bracket) -> list[Avdelning]:
        """All declared avdelningar in a bracket."""
        return [a for a in self.avdelningar if a.bracket is bracket]

    def eighteen_plus_avdelningar(self) -> list[str]:
        """Names of declared 18+ avdelningar — the 'annat' bracket (e.g. Ledare)."""
        return [a.name for a in self.avdelningar if a.bracket is Bracket.ANNAT]
