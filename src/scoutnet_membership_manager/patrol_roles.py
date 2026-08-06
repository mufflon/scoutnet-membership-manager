"""
Patrol-scoped role holders (Patrulledare / Vice patrulledare) and their Scoutnet
profile links (§4, §17).

These are youth roles held inside an avdelning's patrull — never adult
leadership (``Role.is_leader`` deliberately excludes ``patrol`` scope). They
cannot be ended through the API: ``update/membership`` writes only
status / troop_id / patrol_id, and there is no engagement-write endpoint at all
(CLAUDE.md §4). So after an uppflyttning a mover can keep a Patrulledare role in
their *old* patrull, which then has to be ended by hand in Scoutnet — setting a
slutdatum, which moves it to *tidigare uppdrag* rather than deleting it.

This module surfaces exactly that follow-up worklist: for a set of members, who
still holds a patrol-scoped role, with a direct link to their Scoutnet profile so
the operator can open each and end the role by hand.
"""

from __future__ import annotations

from dataclasses import dataclass

from scoutnet_membership_manager.scoutnet.models import PATROL_SCOPE, MemberList

# Scoutnet member profile URL. The path segment is the medlemsnummer (member_no),
# which is what the memberlist keys on. Verify once against a real profile before
# relying on it in the field — Scoutnet's public URL scheme is not in the API spec.
SCOUTNET_USER_URL = "https://scoutnet.se/organisation/user/{member_no}"


def scoutnet_user_url(member_no: str) -> str:
    """The Scoutnet profile URL for a member number."""
    return SCOUTNET_USER_URL.format(member_no=member_no)


@dataclass
class PatrolRoleHolder:
    """One member's patrol-scoped role, with a link to their Scoutnet profile."""

    member_no: str
    name: str
    avdelning: str | None  # the member's current avdelning (unit)
    patrol: str | None  # the member's current patrull placement
    role_name: str  # "Patrulledare" / "Vice patrulledare" as Scoutnet labels it
    url: str


def patrol_role_holders(
    memberlist: MemberList, member_nos: set[str] | None = None
) -> list[PatrolRoleHolder]:
    """
    Every patrol-scoped role held by the given members (or all members when
    ``member_nos`` is ``None``), one row per role, sorted by name. A member with
    both Patrulledare and Vice appears once per role.
    """
    by_no = memberlist.by_member_no()
    nos = member_nos if member_nos is not None else set(by_no)
    holders: list[PatrolRoleHolder] = []
    for no in nos:
        m = by_no.get(no)
        if m is None:
            continue
        for r in m.roles:
            if r.scope != PATROL_SCOPE:
                continue
            holders.append(
                PatrolRoleHolder(
                    member_no=m.member_no,
                    name=m.full_name,
                    avdelning=m.unit,
                    patrol=m.patrol,
                    role_name=r.role_name,
                    url=scoutnet_user_url(m.member_no),
                )
            )
    holders.sort(key=lambda h: (h.name, h.role_name))
    return holders
