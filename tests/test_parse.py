from __future__ import annotations

from karverktyg.scoutnet.models import Member, PaymentBucket, Role
from karverktyg.scoutnet.parse import EXTRA_INFO_PREFIX, parse_memberlist


def test_parses_all_active_members(memberlist):
    assert len(memberlist) == 371
    assert memberlist.current_term_label  # "Höst 2026"
    assert memberlist.prev_term_label  # "Vår 2026"


def test_roles_both_shapes_parse(memberlist):
    """`roles` is `[]` for plain members and an object for role-holders — both
    must parse (§4). Missing this identifies zero leaders."""
    with_roles = [m for m in memberlist.members if m.roles]
    without_roles = [m for m in memberlist.members if not m.roles]
    assert with_roles, "expected some role-holders"
    assert without_roles, "expected some plain members with empty roles"
    # role-holders carry structured troop/group scoped roles
    any_troop = [r for m in with_roles for r in m.roles if r.scope == "troop"]
    assert any_troop
    assert all(r.role_key for r in any_troop)


def test_empty_roles_never_crashes():
    ml = parse_memberlist(
        {
            "data": {"1": {"member_no": {"value": "1"}, "roles": {"value": []}}},
            "labels": {},
        }
    )
    assert ml.members[0].roles == []


def test_extra_info_dropped_at_boundary(memberlist_raw, memberlist):
    """The raw payload contains extra_info_*; none may survive parsing (§4)."""
    raw_has_extra = any(
        f.startswith(EXTRA_INFO_PREFIX)
        for fields in memberlist_raw["data"].values()
        for f in fields
    )
    assert raw_has_extra, "fixture should contain extra_info_* to make this meaningful"
    for m in memberlist.members:
        assert not any(k.startswith(EXTRA_INFO_PREFIX) for k in m.passthrough)


def test_troop_id_from_unit_raw_value(memberlist):
    vikingarna = [m for m in memberlist.members if m.unit == "Vikingarna"]
    assert vikingarna
    assert all(m.unit_troop_id == 10164 for m in vikingarna)


def test_payment_current_not_billed_prev_has_status(memberlist):
    assert all(m.current_payment() is PaymentBucket.NOT_BILLED for m in memberlist.members)
    prev = {m.prev_payment() for m in memberlist.members}
    assert PaymentBucket.SETTLED in prev
    assert PaymentBucket.OUTSTANDING in prev


def test_patrol_leader_is_not_adult_leadership():
    """Patrulledare reuses the 'leader' key but is patrol-scoped -> youth role."""
    patrol = Role("patrol", 36256, 96, "leader", "Patrulledare")
    unit = Role("troop", 10164, 3, "leader", "Avdelningsledare")
    assert patrol.is_leader is False
    assert unit.is_leader is True
    # A member whose only leader-keyed role is the patrol one is not a leader.
    assert Member(member_no="1", roles=[patrol]).is_leader is False
    assert Member(member_no="2", roles=[unit]).is_leader is True


def test_fixture_patrol_leaders_not_counted_as_leaders(memberlist):
    """The Patrulledare / Vice patrulledare in the fixture must not be leaders."""
    patrol_only = [
        m
        for m in memberlist.members
        if any(r.scope == "patrol" for r in m.roles)
        and not any(r.scope != "patrol" and r.is_leader for r in m.roles)
    ]
    assert patrol_only, "fixture should contain patrol-scoped role holders"
    assert all(not m.is_leader for m in patrol_only)


def test_birth_year_parsed(memberlist):
    # adults (leaders) are born decades earlier than the scouts, so the range
    # is wide — just assert every year parses to a plausible value
    years = [m.birth_year for m in memberlist.members if m.birth_year]
    assert years and all(1930 < y <= 2026 for y in years)
