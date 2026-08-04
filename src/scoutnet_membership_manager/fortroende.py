"""
Förtroendeuppdrag — the register of kår-level assignments (§18).

Lists every **group**-scoped role from ``roles.value``: one row per assignment,
a register of posts rather than of people, so a person holding several posts
appears once per post. This blade is pure pass-through — it classifies nothing,
matches nothing, and drops nothing, so an unfamiliar ``role_key`` surfaces by
itself (sorted last) instead of vanishing (§18).

``troop``-scoped roles are avdelning leadership (uppflyttning / findings), and
``patrol``-scoped roles are youth roles (§4); both are excluded here. Match and
sort on ``role_key``; display ``role_name`` (or a configured label override).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from scoutnet_membership_manager.collation import sort_key
from scoutnet_membership_manager.config.models import KarConfig
from scoutnet_membership_manager.scoutnet.models import MemberList

GROUP_SCOPE = "group"

# The blade splits into three sections (§18): the board (most responsibility,
# shown first), the continuous "other" posts, and external-assembly delegates
# (ombud) last. Which role_key falls where is configured, not classified.
BOARD, OTHER, DELEGATE = "board", "other", "delegate"
_SECTION_ORDER = {BOARD: 0, OTHER: 1, DELEGATE: 2}
SECTION_LABEL_SV = {
    BOARD: "Kårstyrelse",
    OTHER: "Övriga förtroendeuppdrag",
    DELEGATE: "Ombud och representanter",
}


@dataclass(frozen=True)
class Assignment:
    """One group-scoped förtroendeuppdrag held by one member."""

    role_key: str
    role_name: str
    label: str  # role_name, unless a config label override applies (§18)
    member_no: str
    member_name: str
    section: str  # board / other / delegate (§18)


@dataclass(frozen=True)
class Vacancy:
    """An expected post with fewer holders than configured (§18, opt-in)."""

    role_key: str
    label: str
    expected: int
    filled: int

    @property
    def missing(self) -> int:
        """How many seats are unfilled (never negative)."""
        return max(0, self.expected - self.filled)


@dataclass
class FortroendeResult:
    """The ordered assignment register plus the totals used for reconciliation."""

    assignments: list[Assignment]
    # Group-scoped assignments — the length of the list shown on the blade.
    group_count: int
    # Roles parsed across *all* scopes (troop + group + patrol), for the
    # independent cross-check against /organisation/group's rolecount (§18).
    total_roles_parsed: int
    vacancies: list[Vacancy] = field(default_factory=list)


def _label(role_key: str, role_name: str, overrides: dict[str, str]) -> str:
    override = overrides.get(role_key)
    return override or role_name or role_key


# Hard-coded section classification, by role_key — uniform for this kår; another
# kår would extend these lists (the operator confirmed hard-coding is fine, §18).
# scout_challenge_rep (Utmanarscoutrepresentant) is a board seat; district_voter
# (Ombud distriktsstämma) is a one-day delegate, not ongoing work.
_BOARD_ORDER = [
    "leader",  # Kårordförande (group-scoped)
    "vice_leader",
    "treasurer",
    "vice_treasurer",
    "secretary",
    "board_member",
    "scout_challenge_rep",
    "board_deputy",
]
_DELEGATE_KEYS = frozenset({"district_voter"})
_OTHER_ORDER = ["nomination_committee", "accountant", "deputy_auditor_group"]


def _section_and_rank(role_key: str) -> tuple[str, int]:
    """
    Which section a role_key belongs to and its rank within it (§18). Anything not
    board/delegate is "other", ranked by ``_OTHER_ORDER`` or last if unlisted —
    pure pass-through, nothing is dropped.
    """
    if role_key in _BOARD_ORDER:
        return BOARD, _BOARD_ORDER.index(role_key)
    if role_key in _DELEGATE_KEYS:
        return DELEGATE, 0
    try:
        return OTHER, _OTHER_ORDER.index(role_key)
    except ValueError:
        return OTHER, len(_OTHER_ORDER)


def fortroendeuppdrag(memberlist: MemberList, config: KarConfig) -> FortroendeResult:
    """Build the sectioned förtroendeuppdrag register from group-scoped roles (§18)."""
    overrides = config.role_label_overrides

    assignments: list[Assignment] = []
    total_roles = 0
    for m in memberlist.members:
        total_roles += len(m.roles)
        for r in m.roles:
            if r.scope != GROUP_SCOPE:
                continue
            section, _ = _section_and_rank(r.role_key)
            assignments.append(
                Assignment(
                    role_key=r.role_key,
                    role_name=r.role_name,
                    label=_label(r.role_key, r.role_name, overrides),
                    member_no=m.member_no,
                    member_name=m.full_name,
                    section=section,
                )
            )

    # Board first, then "other", delegates last; within a section by configured
    # rank, then role_name, then member name under Swedish collation (§18).
    # role_name is the group tiebreak so a section's roles stay together.
    assignments.sort(
        key=lambda a: (
            _SECTION_ORDER[a.section],
            _section_and_rank(a.role_key)[1],
            sort_key(a.role_name),
            sort_key(a.member_name),
        )
    )

    return FortroendeResult(
        assignments=assignments,
        group_count=len(assignments),
        total_roles_parsed=total_roles,
        vacancies=_vacancies(assignments, config),
    )


def group_by_section(assignments: list[Assignment]) -> list[dict]:
    """Group sorted assignments into the three §18 sections, skipping empty ones."""
    out: list[dict] = []
    for section in (BOARD, OTHER, DELEGATE):
        items = [a for a in assignments if a.section == section]
        if items:
            out.append(
                {"section": section, "label": SECTION_LABEL_SV[section], "assignments": items}
            )
    return out


def _vacancies(assignments: list[Assignment], config: KarConfig) -> list[Vacancy]:
    expected = config.expected_fortroende
    if not expected:
        return []
    filled = Counter(a.role_key for a in assignments)
    label_for = {a.role_key: a.label for a in assignments}
    out: list[Vacancy] = []
    for e in expected:
        n_filled = filled.get(e.role_key, 0)
        if n_filled >= e.count:
            continue
        label = (
            e.label
            or config.role_label_overrides.get(e.role_key)
            or label_for.get(e.role_key, e.role_key)
        )
        out.append(Vacancy(role_key=e.role_key, label=label, expected=e.count, filled=n_filled))
    return out


def rolecount_reconciliation(total_roles_parsed: int, rolecount: int | None) -> dict[str, object]:
    """
    Cross-check the parsed role total against /organisation/group's rolecount
    (§18). A mismatch means a scope is being missed or the parse is wrong — the
    same independent-total check that confirmed 369 + 2 = 371 for the memberlist.
    ``rolecount`` is ``None`` when unavailable (e.g. fixture mode synthesises the
    aggregate without it); the check then degrades to "not available" rather than
    claiming a (mis)match.
    """
    return {
        "total_parsed": total_roles_parsed,
        "rolecount": rolecount,
        "available": rolecount is not None,
        "match": rolecount is not None and total_roles_parsed == rolecount,
    }
