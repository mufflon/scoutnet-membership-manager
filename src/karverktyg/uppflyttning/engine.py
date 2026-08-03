"""
Compute the uppflyttning master set (§17).

Only the oldest cohort of each transitioning bracket moves. Adults (18+) and
members of an 18+ avdelning are excluded, never auto-moved — nor is anyone set
as a leader (no automatic leader shifts). A scout who holds a plain non-leader
function elsewhere still shifts with their cohort, flagged for review. Off-cohort
members are flagged and set aside. The Äventyrare → Utmanare move is pending
until a target is elected.
"""

from __future__ import annotations

from karverktyg.collation import sort_key
from karverktyg.config.models import Bracket, KarConfig, TransitionKind
from karverktyg.roster import TroopIndex, build_troop_index
from karverktyg.scoutnet.models import Member, MemberList
from karverktyg.uppflyttning.cohort import resolve_cohort_year
from karverktyg.uppflyttning.models import ElectedTarget, MasterSet, MoveEntry, MoveStatus

_MOVING = {
    TransitionKind.SAME_WEEKDAY,
    TransitionKind.MERGE,
    TransitionKind.NEW_COHORT_AVDELNING,
}

# The age ladder, low to high. A member moves up when their age for cohort year
# N lands them in the *next* bracket's window rather than their current one.
_AGE_LADDER = [
    Bracket.SPARARE,
    Bracket.UPPTACKARE,
    Bracket.AVENTYRARE,
    Bracket.UTMANARE,
    Bracket.ROVER,
]


def _age_bracket(age: int, config: KarConfig) -> Bracket | None:
    """
    Return the lowest bracket whose age window contains ``age``. Lowest resolves the
    Äventyrare/Utmanare boundary overlap (age 14) toward Äventyrare, so a 14-year
    old stays and a 15-year old graduates.
    """
    for b in _AGE_LADDER:
        try:
            rule = config.rule(b)
        except KeyError:
            continue
        if (
            rule.age_min is not None
            and rule.age_max is not None
            and rule.age_min <= age <= rule.age_max
        ):
            return b
    return None


def _next_bracket(b: Bracket) -> Bracket | None:
    i = _AGE_LADDER.index(b)
    return _AGE_LADDER[i + 1] if i + 1 < len(_AGE_LADDER) else None


def _is_excluded(m: Member, n: int, eighteen_plus: set[str]) -> str | None:
    """
    Reason a moving-cohort member is excluded from the auto-move set, or None.

    A leader is never auto-shifted (no automatic leader moves): being set as a
    leader in an avdelning keeps the member there. Adults (18+) and members of an
    18+ avdelning are also excluded. A plain *non-leader* role (e.g. a functionary)
    does NOT exclude a scout — they shift with their cohort, flagged with a note.
    """
    if m.is_leader:
        return "Satt som ledare i en avdelning – flyttas ej (inga automatiska ledarförflyttningar)"
    if m.birth_year is not None and (n - m.birth_year) >= 18:  # noqa: PLR2004
        return "Myndig (18+) – flyttas ej, granska"
    if m.unit in eighteen_plus:
        return "I en 18+-avdelning – flyttas ej, granska"
    return None


def _base(
    m: Member,
    transition: TransitionKind,
    status: MoveStatus,
    target_name: str | None,
    target_id: int | None,
    note: str,
) -> MoveEntry:
    return MoveEntry(
        member_no=m.member_no,
        member_name=m.full_name,
        birth_year=m.birth_year,
        source_avdelning=m.unit,
        source_troop_id=m.unit_troop_id,
        target_avdelning=target_name,
        target_troop_id=target_id,
        transition=transition,
        status=status,
        note=note,
        default_target=target_name,
    )


def _resolve_target(
    m: Member,
    transition: TransitionKind,
    config: KarConfig,
    index: TroopIndex,
    n: int,
    elected_target: ElectedTarget | None = None,
) -> MoveEntry:
    if transition in (TransitionKind.SAME_WEEKDAY, TransitionKind.MERGE):
        source = config.avdelning(m.unit) if m.unit else None
        target_name = source.default_target if source else None
        target_id = index.name_to_id.get(target_name) if target_name else None
    elif elected_target is not None:  # NEW_COHORT_AVDELNING — operator elected it
        target_name = elected_target.avdelning
        target_id = elected_target.troop_id or index.name_to_id.get(target_name)
    else:  # NEW_COHORT_AVDELNING — fall back to config cohort_year
        target_a = config.target_for_cohort(Bracket.UTMANARE, n)
        target_name = target_a.name if target_a else None
        target_id = index.name_to_id.get(target_name) if target_name else None

    if target_name is None:
        return _base(
            m,
            transition,
            MoveStatus.PENDING_TARGET,
            None,
            None,
            f"Ingen måldelning vald för årskull {n} – välj en Utmanare-avdelning ovan",
        )
    if target_id is None:
        return _base(
            m,
            transition,
            MoveStatus.PENDING_TARGET,
            target_name,
            None,
            f"Måldelningen {target_name!r} saknar troop_id (ny/tom avdelning?) – "
            "ange troop_id vid val",
        )
    return _base(m, transition, MoveStatus.READY, target_name, target_id, "")


def compute_master_set(  # noqa: C901 - per-member classification is inherently branchy
    memberlist: MemberList,
    config: KarConfig,
    config_cohort_year_n: int | None,
    current_term_label: str | None = None,
    index: TroopIndex | None = None,
    elected_target: ElectedTarget | None = None,
) -> MasterSet:
    """Compute master set."""
    n = resolve_cohort_year(
        config_cohort_year_n, current_term_label or memberlist.current_term_label
    )
    if index is None:
        index = build_troop_index(memberlist, config)
    eighteen_plus = set(config.eighteen_plus_avdelningar())

    entries: list[MoveEntry] = []
    for m in memberlist.members:
        bracket = m.bracket
        if bracket is None:
            continue
        try:
            rule = config.rule(bracket)
        except KeyError:
            continue
        if rule.transition not in _MOVING or rule.age_min is None or rule.age_max is None:
            continue

        if m.birth_year is None:
            entries.append(
                _base(
                    m,
                    rule.transition,
                    MoveStatus.OFF_COHORT,
                    None,
                    None,
                    "Okänt födelseår – kan inte placeras i årskull",
                )
            )
            continue

        age = n - m.birth_year
        correct_bracket = _age_bracket(age, config)
        target_bracket = _next_bracket(bracket)

        if correct_bracket is bracket:
            continue  # age still fits the current bracket — stays put

        if correct_bracket is not target_bracket:
            # too young for the bracket, or more than one step over (e.g. a
            # 2014-born still in Spårare) — manual, excluded from the move set
            entries.append(
                _base(
                    m,
                    rule.transition,
                    MoveStatus.OFF_COHORT,
                    None,
                    None,
                    f"Född {m.birth_year} (ålder {age} år {n}) – utanför {bracket}, "
                    "kräver manuell hantering",
                )
            )
            continue

        # Aged into the next bracket — this is the moving cohort.
        reason = _is_excluded(m, n, eighteen_plus)
        if reason is not None:
            entries.append(_base(m, rule.transition, MoveStatus.EXCLUDED, None, None, reason))
            continue

        entry = _resolve_target(m, rule.transition, config, index, n, elected_target)
        if m.is_role_holder:
            extra = "har även en funktion i annan avdelning – kontrollera"
            entry.note = f"{entry.note} · {extra}" if entry.note else extra.capitalize()
        entries.append(entry)

    entries.sort(
        key=lambda e: (
            sort_key(e.target_avdelning or "~"),
            sort_key(e.member_name),
        )
    )
    return MasterSet(cohort_year=n, entries=entries)


# The operator runs one transition group at a time (§7 Deferred architecture A).
MISPLACED_GROUP = "misplaced"


def scope_master_set(master: MasterSet, group: str | None) -> MasterSet:
    """
    Narrow the master set to one group so it can be viewed, exported and written
    on its own. ``group`` is a TransitionKind value (its correctly-aged movers,
    with off-cohort members excluded), or ``"misplaced"`` (the off-cohort members
    of any bracket — wrong age, handled per person), or None/"all" for everything.
    """
    if group in (None, "all"):
        return master
    if group == MISPLACED_GROUP:
        entries = [e for e in master.entries if e.status is MoveStatus.OFF_COHORT]
    else:
        entries = [
            e
            for e in master.entries
            if str(e.transition) == group and e.status is not MoveStatus.OFF_COHORT
        ]
    return MasterSet(cohort_year=master.cohort_year, entries=entries)
