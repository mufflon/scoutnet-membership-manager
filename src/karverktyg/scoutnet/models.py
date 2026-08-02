"""In-memory Scoutnet models and payment classification (§4).

These hold live data including personal fields; they are never persisted — the
database stores only workflow state keyed on ``member_no`` (§9). ``extra_info_*``
is dropped before a Member is constructed (§4, GDPR Art. 9) and cannot appear
here at all.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field

from karverktyg.config.models import Bracket, bracket_by_unit_type_code

# --- Field classification (§4) --------------------------------------------
EMAIL_FIELDS = frozenset({
    "email", "contact_email", "contact_alt_email", "contact_scouterna-email",
    "contact_email_dad", "contact_email_mum",
})
PHONE_FIELDS = frozenset({
    "contact_home_phone", "contact_work_phone", "contact_mobile_phone",
    "contact_mobile_dad", "contact_mobile_mum",
    "contact_telephone_dad", "contact_telephone_mum",
})
GUARDIAN_EMAIL_FIELDS = ("contact_email_dad", "contact_email_mum")

# Default set of role_keys that count as "leader" for finding purposes (§11).
LEADER_ROLE_KEYS = frozenset({"leader", "other_leader", "assistant_leader"})

# Fields we parse into typed attributes; not carried again in passthrough.
_PARSED_FIELDS = frozenset({
    "member_no", "first_name", "last_name", "date_of_birth", "sex", "status",
    "unit", "unit_type", "patrol", "roles", "current_term", "prev_term",
    "group", "group_role", "unit_role",
}) | EMAIL_FIELDS | PHONE_FIELDS


class PaymentBucket(enum.StrEnum):
    NOT_BILLED = "not_billed"
    OUTSTANDING = "outstanding"
    SETTLED = "settled"
    UNKNOWN = "unknown"


# Explicit allowlists (§4). Only *observed* codes are classified; anything else
# routes to UNKNOWN (review) rather than being guessed into settled/outstanding.
_SETTLED_CODES = frozenset({"paid"})
_NOT_BILLED_CODES = frozenset({"not_invoiced"})
_OUTSTANDING_CODES = frozenset({"unpaid_overdue_reminded", "paid_partial_credit"})


def classify_payment(code: str | None) -> PaymentBucket:
    if code is None:
        return PaymentBucket.UNKNOWN
    if code in _SETTLED_CODES:
        return PaymentBucket.SETTLED
    if code in _NOT_BILLED_CODES:
        return PaymentBucket.NOT_BILLED
    if code in _OUTSTANDING_CODES:
        return PaymentBucket.OUTSTANDING
    return PaymentBucket.UNKNOWN


@dataclass(frozen=True)
class Role:
    """One role assignment from ``roles.value`` (§4). ``scope`` is "troop" or
    "group"; ``scope_id`` is the troop_id or group_id it is scoped to."""

    scope: str
    scope_id: int
    role_id: int
    role_key: str
    role_name: str

    @property
    def is_leader(self) -> bool:
        return self.role_key in LEADER_ROLE_KEYS


@dataclass
class Member:
    member_no: str
    first_name: str = ""
    last_name: str = ""
    date_of_birth: str | None = None
    birth_year: int | None = None
    sex_code: str | None = None
    status_code: str | None = None

    unit: str | None = None
    unit_troop_id: int | None = None
    unit_type_code: int | None = None
    patrol: str | None = None
    patrol_id: int | None = None

    roles: list[Role] = field(default_factory=list)

    current_term_code: str | None = None
    prev_term_code: str | None = None
    current_term_label: str | None = None
    prev_term_label: str | None = None

    emails: dict[str, str] = field(default_factory=dict)
    phones: dict[str, str] = field(default_factory=dict)
    passthrough: dict[str, object] = field(default_factory=dict)

    # --- Derived helpers ---------------------------------------------------
    @property
    def bracket(self) -> Bracket | None:
        return bracket_by_unit_type_code(self.unit_type_code)

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_role_holder(self) -> bool:
        return bool(self.roles)

    @property
    def is_leader(self) -> bool:
        return any(r.is_leader for r in self.roles)

    def troop_ids_with_role(self) -> set[int]:
        return {r.scope_id for r in self.roles if r.scope == "troop"}

    def avdelning_troop_ids(self) -> set[int]:
        """All troop_ids this member is attached to — primary ``unit`` plus any
        troop-scoped role (§11 multi-avdelning)."""
        ids = set(self.troop_ids_with_role())
        if self.unit_troop_id is not None:
            ids.add(self.unit_troop_id)
        return ids

    def current_payment(self) -> PaymentBucket:
        return classify_payment(self.current_term_code)

    def prev_payment(self) -> PaymentBucket:
        return classify_payment(self.prev_term_code)


@dataclass
class MemberList:
    members: list[Member]
    current_term_label: str | None = None
    prev_term_label: str | None = None
    variant: str = "active"

    def __len__(self) -> int:
        return len(self.members)

    def by_member_no(self) -> dict[str, Member]:
        return {m.member_no: m for m in self.members}
