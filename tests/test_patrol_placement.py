from __future__ import annotations

from scoutnet_membership_manager.patrol_roles import patrol_role_holders, scoutnet_user_url
from scoutnet_membership_manager.roster import build_patrol_index
from scoutnet_membership_manager.scoutnet.models import Member, MemberList, Role


def _m(no, unit_troop_id=None, patrol_id=None, patrol=None, roles=None, unit=None):
    return Member(
        member_no=no,
        unit=unit,
        unit_troop_id=unit_troop_id,
        patrol=patrol,
        patrol_id=patrol_id,
        roles=roles or [],
    )


def test_first_known_patrol_is_lowest_id_and_none_when_empty():
    ml = MemberList(
        members=[
            _m("1", unit_troop_id=20, patrol_id=900, patrol="Räven"),
            _m("2", unit_troop_id=20, patrol_id=500, patrol="Örnen"),
            _m("3", unit_troop_id=20, patrol_id=500, patrol="Örnen"),
            _m("4", unit_troop_id=30, patrol_id=None),  # no patrull -> not indexed
        ]
    )
    idx = build_patrol_index(ml)

    first = idx.first_known_patrol(20)
    assert first is not None
    assert first.patrol_id == 500 and first.name == "Örnen" and first.size == 2  # lowest id first
    # Troop 30 has no member placed in a patrull -> undiscoverable -> None.
    assert idx.first_known_patrol(30) is None
    # A troop we have never seen, and None, both yield None.
    assert idx.first_known_patrol(999) is None
    assert idx.first_known_patrol(None) is None


def test_patrol_role_holders_only_patrol_scope_with_links():
    patrulledare = Role("patrol", 500, 2, "leader", "Patrulledare")
    vice = Role("patrol", 500, 3, "vice_leader", "Vice patrulledare")
    adult = Role("troop", 20, 9, "assistant_leader", "Ledare")  # not patrol scope
    ml = MemberList(
        members=[
            _m("1", unit="Utmanarna", patrol="Örnen", roles=[patrulledare, adult]),
            _m("2", unit="Utmanarna", patrol="Örnen", roles=[vice]),
            _m("3", unit="Utmanarna", roles=[adult]),  # only adult role -> excluded
        ]
    )

    holders = patrol_role_holders(ml, {"1", "2", "3"})

    assert [(h.member_no, h.role_name) for h in holders] == [
        ("1", "Patrulledare"),
        ("2", "Vice patrulledare"),
    ]
    assert holders[0].url == scoutnet_user_url("1") == "https://scoutnet.se/organisation/user/1"
    assert holders[0].avdelning == "Utmanarna" and holders[0].patrol == "Örnen"


def test_patrol_role_holders_scopes_to_given_members():
    ml = MemberList(
        members=[
            _m("1", roles=[Role("patrol", 500, 2, "leader", "Patrulledare")]),
            _m("2", roles=[Role("patrol", 500, 2, "leader", "Patrulledare")]),
        ]
    )
    # Only member 1 is in the selection.
    holders = patrol_role_holders(ml, {"1"})
    assert [h.member_no for h in holders] == ["1"]
