from __future__ import annotations

from karverktyg.findings import compute_findings
from karverktyg.findings.models import FindingType, Severity, value_hash
from karverktyg.scoutnet.models import Member, MemberList, Role


def _mk(member_no, unit, code, troop, birth_year, roles=(), phones=None, emails=None):
    m = Member(member_no=member_no, unit=unit, unit_type_code=code,
               unit_troop_id=troop, birth_year=birth_year)
    m.roles = list(roles)
    m.phones = phones or {}
    m.emails = emails or {}
    return m


def test_value_hash_stability():
    assert value_hash("a@b.se ") == value_hash("A@B.SE")  # whitespace + case normalised
    assert value_hash("a@b.se") != value_hash("c@d.se")  # distinct values differ


def test_findings_types_fire(config):
    ledare_troop = 10172  # Ledare avdelning id
    ml = MemberList(members=[
        # populate the index so "Ledare" resolves to its troop id
        _mk("led_resident", "Ledare", 7, ledare_troop, 1980),
        _mk("kamp_resident", "Kämparna", 3, 200, 2015),
        # 1. leader role scoped to Ledare -> SECURITY
        _mk("sec", "Ledare", 7, ledare_troop, 1975,
            roles=[Role("troop", ledare_troop, 3, "other_leader", "Ledare")]),
        # 2. adult in a scout avdelning
        _mk("adult", "Hajarna", 2, 100, 1998),
        # 3. multi-avdelning: Hajarna primary + troop role in Kämparna
        _mk("multi", "Hajarna", 2, 100, 2017,
            roles=[Role("troop", 200, 5, "assistant_leader", "Assisterande ledare")]),
        # 4. no avdelning
        _mk("none", None, None, None, 2016),
        # 5. data quality
        _mk("bad", "Hajarna", 2, 100, 2017, phones={"contact_mobile_phone": "123"},
            emails={"email": "not-an-email"}),
    ])
    findings = compute_findings(ml, config, cohort_year_n=2026)
    kinds = {f.type for f in findings}
    assert FindingType.SECURITY_LEDARE_LEADER in kinds
    assert FindingType.ADULT_IN_SCOUT_UNIT in kinds
    assert FindingType.MULTI_AVDELNING in kinds
    assert FindingType.NO_AVDELNING in kinds
    assert FindingType.BAD_PHONE in kinds
    assert FindingType.BAD_EMAIL in kinds

    sec = [f for f in findings if f.type is FindingType.SECURITY_LEDARE_LEADER]
    assert all(f.severity is Severity.SECURITY for f in sec)


def test_utmanare_rover_exempt_from_structural(config):
    """Utmanare/Rover: no age check, no multi-avdelning check (§11, §17)."""
    ml = MemberList(members=[
        _mk("u_resident", "Fniss", 5, 500, 2005),
        _mk("r_resident", "Finness", 6, 600, 1990),
        # an 'adult' Utmanare and a multi-avdelning Rover — neither should flag
        _mk("old_utmanare", "Fniss", 5, 500, 1990),
        _mk("multi_rover", "Finness", 6, 600, 1995,
            roles=[Role("troop", 500, 5, "assistant_leader", "x")]),
    ])
    findings = compute_findings(ml, config, cohort_year_n=2026)
    kinds = {f.type for f in findings}
    assert FindingType.ADULT_IN_SCOUT_UNIT not in kinds
    assert FindingType.MULTI_AVDELNING not in kinds


def test_findings_on_fixture_smoke(memberlist, config):
    findings = compute_findings(memberlist, config, cohort_year_n=2026)
    by_type = {}
    for f in findings:
        by_type.setdefault(f.type, 0)
        by_type[f.type] += 1
    # the two no-avdelning members are present in live data
    assert by_type.get(FindingType.NO_AVDELNING) == 2
