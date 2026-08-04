"""
Parse a raw ``GET /group/memberlist`` payload into typed models (§4).

Handles the observed quirks explicitly:
  * every field is wrapped as ``{value}`` or ``{value, raw_value}``;
  * ``roles`` arrives as ``[]`` for plain members and as an object for
    role-holders — both are accepted;
  * ``extra_info_*`` is dropped here, at the client boundary, so it can never
    enter the model, a snapshot or an export (GDPR Art. 9);
  * unknown fields are preserved in ``passthrough`` (never silently dropped),
    minus ``extra_info_*``.
"""

from __future__ import annotations

import re
from typing import Any

from scoutnet_membership_manager.scoutnet.models import (
    _PARSED_FIELDS,
    EMAIL_FIELDS,
    NAME_FIELDS,
    PHONE_FIELDS,
    DueDate,
    Member,
    MemberList,
    Role,
)

EXTRA_INFO_PREFIX = "extra_info_"

# A reminder-shifted due date renders as "2026-04-30 (2026-02-28)" (§4).
_DUE_SHIFT = re.compile(r"^\s*(\S+)\s*\(([^)]+)\)\s*$")


def parse_due_date(raw: Any) -> DueDate:
    """
    Parse a term due date, retaining **both** dates when a reminder shifted it
    (§4): ``"2026-04-30 (2026-02-28)"`` -> current 2026-04-30, original
    2026-02-28. A plain date has no original; empty/missing yields an empty
    DueDate.
    """
    if raw is None:
        return DueDate()
    s = str(raw).strip()
    if not s:
        return DueDate()
    m = _DUE_SHIFT.match(s)
    if m:
        return DueDate(current=m.group(1), original=m.group(2).strip())
    return DueDate(current=s)


def _value(wrapper: Any) -> Any:
    if isinstance(wrapper, dict):
        return wrapper.get("value")
    return wrapper


def _raw(wrapper: Any) -> Any:
    if isinstance(wrapper, dict):
        return wrapper.get("raw_value", wrapper.get("value"))
    return wrapper


def _int_or_none(v: Any) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _birth_year(dob: Any) -> int | None:
    if not isinstance(dob, str) or len(dob) < 4:  # noqa: PLR2004 - 4-digit year
        return None
    return _int_or_none(dob[:4])


def _parse_roles(wrapper: Any) -> list[Role]:
    """Accept both the empty-list and the object form of ``roles.value``."""
    value = _value(wrapper)
    if not isinstance(value, dict):  # [] (plain member) or missing
        return []
    roles: list[Role] = []
    for scope, by_scope_id in value.items():
        if not isinstance(by_scope_id, dict):
            continue
        for scope_id, by_role_id in by_scope_id.items():
            sid = _int_or_none(scope_id)
            if sid is None or not isinstance(by_role_id, dict):
                continue
            for role in by_role_id.values():
                if not isinstance(role, dict):
                    continue
                roles.append(
                    Role(
                        scope=str(scope),
                        scope_id=sid,
                        role_id=_int_or_none(role.get("role_id")) or 0,
                        role_key=str(role.get("role_key", "")),
                        role_name=str(role.get("role_name", "")),
                    )
                )
    return roles


def _apply_terms(m: Member, fields: dict[str, Any]) -> None:
    """Per-term payment status, due dates and the payment reference (§4)."""
    m.current_term_code = _raw(fields.get("current_term")) if "current_term" in fields else None
    m.prev_term_code = _raw(fields.get("prev_term")) if "prev_term" in fields else None
    # Swedish display for each term's status; key logic on the code, show this (§4).
    m.current_term_value = _value(fields.get("current_term")) if "current_term" in fields else None
    m.prev_term_value = _value(fields.get("prev_term")) if "prev_term" in fields else None
    m.current_term_due = parse_due_date(_value(fields.get("current_term_due_date")))
    m.prev_term_due = parse_due_date(_value(fields.get("prev_term_due_date")))
    kid = _value(fields.get("kid"))
    m.kid = str(kid) if kid else None


def _apply_contacts(m: Member, fields: dict[str, Any]) -> None:
    """Emails, phones and guardian names, each in its own passthrough-free map."""
    for target, names in (
        (m.emails, EMAIL_FIELDS),
        (m.phones, PHONE_FIELDS),
        (m.guardian_names, NAME_FIELDS),
    ):
        for f in names:
            if f in fields:
                v = _value(fields[f])
                if v:
                    target[f] = str(v)


def parse_member(member_no: str, fields: dict[str, Any]) -> Member:
    """Parse member."""
    m = Member(member_no=str(_value(fields.get("member_no")) or member_no))
    m.first_name = str(_value(fields.get("first_name")) or "")
    m.last_name = str(_value(fields.get("last_name")) or "")
    m.date_of_birth = _value(fields.get("date_of_birth"))
    m.birth_year = _birth_year(m.date_of_birth)
    m.sex_code = _raw(fields.get("sex")) if "sex" in fields else None
    m.status_code = _raw(fields.get("status")) if "status" in fields else None

    m.unit = _value(fields.get("unit"))
    m.unit_troop_id = _int_or_none(_raw(fields.get("unit"))) if "unit" in fields else None
    if "unit_type" in fields:
        m.unit_type_code = _int_or_none(_raw(fields.get("unit_type")))
    m.patrol = _value(fields.get("patrol"))
    m.patrol_id = _int_or_none(_raw(fields.get("patrol"))) if "patrol" in fields else None

    m.roles = _parse_roles(fields.get("roles"))
    _apply_terms(m, fields)
    _apply_contacts(m, fields)

    # Preserve unknown fields, minus the forbidden extra_info_* (§4).
    for f, wrapper in fields.items():
        if f in _PARSED_FIELDS or f.startswith(EXTRA_INFO_PREFIX):
            continue
        m.passthrough[f] = _value(wrapper)
    return m


def parse_memberlist(raw: dict[str, Any], variant: str = "active") -> MemberList:
    """Parse memberlist."""
    data = raw.get("data")
    if not isinstance(data, dict):
        raise ValueError("memberlist payload has no 'data' object")  # noqa: TRY004
    labels = raw.get("labels") or {}

    members = [
        parse_member(mno, fields) for mno, fields in data.items() if isinstance(fields, dict)
    ]

    ml = MemberList(
        members=members,
        current_term_label=labels.get("current_term"),
        prev_term_label=labels.get("prev_term"),
        variant=variant,
    )
    for m in members:
        m.current_term_label = ml.current_term_label
        m.prev_term_label = ml.prev_term_label
    return ml
