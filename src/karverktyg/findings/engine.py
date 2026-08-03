"""Compute findings live from a memberlist (§11).

Membership-roll checks (age, multi-avdelning) apply only to Spårare, Upptäckare
and Äventyrare — Utmanare and Rover are exempt (§11, §17). Data-quality checks
(phone, email) apply to everyone.
"""

from __future__ import annotations

import phonenumbers
from email_validator import EmailNotValidError, validate_email

from karverktyg.config.models import Bracket, KarConfig
from karverktyg.findings.models import Finding, FindingType, Severity, value_hash
from karverktyg.roster import TroopIndex, build_troop_index
from karverktyg.scoutnet.models import Member, MemberList


def phone_looks_valid(raw: str) -> bool:
    try:
        return phonenumbers.is_valid_number(phonenumbers.parse(raw, "SE"))
    except phonenumbers.NumberParseException:
        return False


def email_looks_valid(raw: str) -> bool:
    try:
        validate_email(raw, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False


def _finding(ftype, sev, m: Member, avdelning, detail, value) -> Finding:
    return Finding(
        type=ftype,
        severity=sev,
        member_no=m.member_no,
        member_name=m.full_name,
        avdelning=avdelning,
        detail=detail,
        value_hash=value_hash(value),
    )


def compute_findings(
    memberlist: MemberList,
    config: KarConfig,
    cohort_year_n: int | None,
    index: TroopIndex | None = None,
) -> list[Finding]:
    if index is None:
        index = build_troop_index(memberlist, config)

    ledare_ids = {
        index.name_to_id[a.name]
        for a in config.avdelningar
        if a.bracket is Bracket.ANNAT and a.name in index.name_to_id
    }
    structural = {r.bracket for r in config.brackets if r.structural_checks}
    rover_ids = index.ids_for_bracket(Bracket.ROVER)

    findings: list[Finding] = []
    for m in memberlist.members:
        # 1. Security: a leader role scoped to the Ledare avdelning (§11, top).
        for r in m.roles:
            if r.scope == "troop" and r.scope_id in ledare_ids and r.is_leader:
                findings.append(_finding(
                    FindingType.SECURITY_LEDARE_LEADER, Severity.SECURITY, m, m.unit,
                    f"Leader role '{r.role_name}' in the Ledare avdelning grants edit "
                    "rights over every adult in the kår.",
                    f"{r.scope_id}:{r.role_key}",
                ))
                break

        # 4. No avdelning at all.
        if not m.unit:
            findings.append(_finding(
                FindingType.NO_AVDELNING, Severity.WARNING, m, None,
                "Member has no avdelning; needs manual resolution.",
                m.member_no,
            ))

        # 2 & 3. Structural checks — Spårare/Upptäckare/Äventyrare only.
        if m.bracket in structural:
            if cohort_year_n and m.birth_year and (cohort_year_n - m.birth_year) >= 18:
                findings.append(_finding(
                    FindingType.ADULT_IN_SCOUT_UNIT, Severity.WARNING, m, m.unit,
                    f"Turns {cohort_year_n - m.birth_year} in cohort year {cohort_year_n} "
                    "while in a scout avdelning.",
                    str(m.birth_year),
                ))
            member_troops = {t for t in m.avdelning_troop_ids() if t not in rover_ids}
            if len(member_troops) > 1:
                names = sorted(index.id_to_name.get(t, str(t)) for t in member_troops)
                findings.append(_finding(
                    FindingType.MULTI_AVDELNING, Severity.WARNING, m, m.unit,
                    "In more than one avdelning: " + ", ".join(names)
                    + " — flag for review, never auto-move.",
                    ",".join(str(t) for t in sorted(member_troops)),
                ))

        # 5. Data quality — everyone.
        for raw in m.phones.values():
            if not phone_looks_valid(raw):
                findings.append(_finding(
                    FindingType.BAD_PHONE, Severity.INFO, m, m.unit,
                    "Phone number does not parse as a valid Swedish number.", raw,
                ))
        for raw in m.emails.values():
            if not email_looks_valid(raw):
                findings.append(_finding(
                    FindingType.BAD_EMAIL, Severity.INFO, m, m.unit,
                    "Email address does not look valid.", raw,
                ))
    return findings
