"""
Compute findings live from a memberlist (§11).

Membership-roll checks (age, multi-avdelning) apply only to Spårare, Upptäckare
and Äventyrare — Utmanare and Rover are exempt (§11, §17). Data-quality checks
(phone, email) apply to everyone.
"""

from __future__ import annotations

import re

import phonenumbers
from email_validator import EmailNotValidError, validate_email

from scoutnet_membership_manager.config.models import BRACKETS, Bracket, KarConfig
from scoutnet_membership_manager.findings.models import Finding, FindingType, Severity, value_hash
from scoutnet_membership_manager.roster import TroopIndex, build_troop_index
from scoutnet_membership_manager.scoutnet.models import Member, MemberList

ADULT_AGE = 18


def phone_looks_valid(raw: str) -> bool:
    """
    Whether a string is a valid phone number — Swedish, or a valid **international**
    number (§11). A foreign number entered without the leading ``+`` (e.g. a
    ``972…`` Israeli mobile) parses as Swedish and fails, so we retry it as an
    international number (which only succeeds when it starts with a real country
    code — a malformed Swedish ``07…`` number stays invalid).
    """
    try:
        if phonenumbers.is_valid_number(phonenumbers.parse(raw, "SE")):
            return True
    except phonenumbers.NumberParseException:
        pass
    digits = re.sub(r"\D", "", raw)
    if not digits or raw.lstrip().startswith("0"):
        return False  # a leading 0 is a national prefix, not a country code
    try:
        return phonenumbers.is_valid_number(phonenumbers.parse("+" + digits, None))
    except phonenumbers.NumberParseException:
        return False


def email_looks_valid(raw: str) -> bool:
    """Whether a string is a syntactically valid email (no deliverability check)."""
    try:
        validate_email(raw, check_deliverability=False)
    except EmailNotValidError:
        return False
    else:
        return True


def _finding(
    ftype: FindingType,
    sev: Severity,
    m: Member,
    avdelning: str | None,
    detail: str,
    value: str,
) -> Finding:
    return Finding(
        type=ftype,
        severity=sev,
        member_no=m.member_no,
        member_name=m.full_name,
        avdelning=avdelning,
        detail=detail,
        value_hash=value_hash(value),
    )


def _security_findings(m: Member, ledare_ids: set[int]) -> list[Finding]:
    for r in m.roles:
        if r.scope == "troop" and r.scope_id in ledare_ids and r.is_leader:
            return [
                _finding(
                    FindingType.SECURITY_LEDARE_LEADER,
                    Severity.SECURITY,
                    m,
                    m.unit,
                    f"Leader role '{r.role_name}' in the Ledare avdelning grants edit "
                    "rights over every adult in the kår.",
                    f"{r.scope_id}:{r.role_key}",
                )
            ]
    return []


def _structural_findings(
    m: Member, cohort_year_n: int | None, index: TroopIndex, rover_ids: set[int]
) -> list[Finding]:
    out: list[Finding] = []
    if m.is_leader:
        out.append(
            _finding(
                FindingType.YOUNG_LEADER,
                Severity.WARNING,
                m,
                m.unit,
                "Ung scout (Äventyrare eller yngre) är satt som ledare – ska inte förekomma.",
                ",".join(sorted(r.role_key for r in m.roles if r.is_leader)),
            )
        )
    if cohort_year_n and m.birth_year and (cohort_year_n - m.birth_year) >= ADULT_AGE:
        out.append(
            _finding(
                FindingType.ADULT_IN_SCOUT_UNIT,
                Severity.WARNING,
                m,
                m.unit,
                f"Turns {cohort_year_n - m.birth_year} in cohort year {cohort_year_n} "
                "while in a scout avdelning.",
                str(m.birth_year),
            )
        )
    member_troops = {t for t in m.avdelning_troop_ids() if t not in rover_ids}
    if len(member_troops) > 1:
        names = sorted(index.id_to_name.get(t, str(t)) for t in member_troops)
        out.append(
            _finding(
                FindingType.MULTI_AVDELNING,
                Severity.WARNING,
                m,
                m.unit,
                "In more than one avdelning: "
                + ", ".join(names)
                + " — flag for review, never auto-move.",
                ",".join(str(t) for t in sorted(member_troops)),
            )
        )
    return out


def _data_quality_findings(m: Member) -> list[Finding]:
    out: list[Finding] = []
    out.extend(
        _finding(
            FindingType.BAD_PHONE,
            Severity.INFO,
            m,
            m.unit,
            "Phone number is not a valid Swedish or international number.",
            raw,
        )
        for raw in m.phones.values()
        if not phone_looks_valid(raw)
    )
    out.extend(
        _finding(
            FindingType.BAD_EMAIL,
            Severity.INFO,
            m,
            m.unit,
            "Email address does not look valid.",
            raw,
        )
        for raw in m.emails.values()
        if not email_looks_valid(raw)
    )
    return out


def compute_findings(
    memberlist: MemberList,
    config: KarConfig,
    cohort_year_n: int | None,
    index: TroopIndex | None = None,
) -> list[Finding]:
    """Compute all findings for a memberlist, live and unstored (§11)."""
    if index is None:
        index = build_troop_index(memberlist, config)

    ledare_ids = {
        index.name_to_id[a.name]
        for a in config.avdelningar
        if a.bracket is Bracket.ANNAT and a.name in index.name_to_id
    }
    structural = {r.bracket for r in BRACKETS if r.structural_checks}
    rover_ids = index.ids_for_bracket(Bracket.ROVER)

    findings: list[Finding] = []
    for m in memberlist.members:
        findings.extend(_security_findings(m, ledare_ids))
        if not m.unit:
            findings.append(
                _finding(
                    FindingType.NO_AVDELNING,
                    Severity.WARNING,
                    m,
                    None,
                    "Member has no avdelning; needs manual resolution.",
                    m.member_no,
                )
            )
        # A minor sitting in the Ledare (18+) avdelning — a placement/permission
        # anomaly the leaders very much want surfaced. The structural-bracket checks
        # above skip Ledare (bracket "annat"), so it is caught here explicitly.
        elif (
            m.unit_troop_id in ledare_ids
            and cohort_year_n
            and m.birth_year
            and (cohort_year_n - m.birth_year) < ADULT_AGE
        ):
            findings.append(
                _finding(
                    FindingType.UNDERAGE_IN_LEDARE,
                    Severity.WARNING,
                    m,
                    m.unit,
                    f"Under 18 (fyller {cohort_year_n - m.birth_year} år {cohort_year_n}) "
                    "men medlem i avdelningen Ledare – ska granskas/flyttas.",
                    str(m.birth_year),
                )
            )
        if m.bracket in structural:
            findings.extend(_structural_findings(m, cohort_year_n, index, rover_ids))
        findings.extend(_data_quality_findings(m))
    return findings
