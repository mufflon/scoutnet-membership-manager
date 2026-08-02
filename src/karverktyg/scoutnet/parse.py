"""Parse a raw ``GET /group/memberlist`` payload into typed models (§4).

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

from typing import Any

from karverktyg.scoutnet.models import (
    _PARSED_FIELDS,
    EMAIL_FIELDS,
    PHONE_FIELDS,
    Member,
    MemberList,
    Role,
)

EXTRA_INFO_PREFIX = "extra_info_"


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
    if not isinstance(dob, str) or len(dob) < 4:
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


def parse_member(member_no: str, fields: dict[str, Any]) -> Member:
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

    m.current_term_code = _raw(fields.get("current_term")) if "current_term" in fields else None
    m.prev_term_code = _raw(fields.get("prev_term")) if "prev_term" in fields else None

    for f in EMAIL_FIELDS:
        if f in fields:
            v = _value(fields[f])
            if v:
                m.emails[f] = str(v)
    for f in PHONE_FIELDS:
        if f in fields:
            v = _value(fields[f])
            if v:
                m.phones[f] = str(v)

    # Preserve unknown fields, minus the forbidden extra_info_* (§4).
    for f, wrapper in fields.items():
        if f in _PARSED_FIELDS or f.startswith(EXTRA_INFO_PREFIX):
            continue
        m.passthrough[f] = _value(wrapper)
    return m


def parse_memberlist(raw: dict[str, Any], variant: str = "active") -> MemberList:
    data = raw.get("data")
    if not isinstance(data, dict):
        raise ValueError("memberlist payload has no 'data' object")
    labels = raw.get("labels") or {}

    members = [parse_member(mno, fields) for mno, fields in data.items()
               if isinstance(fields, dict)]

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
