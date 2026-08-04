"""Finding model (§11). One model, two categories, all advisory."""

from __future__ import annotations

import enum
import hashlib
from dataclasses import dataclass


class Severity(enum.StrEnum):
    """Severity."""

    SECURITY = "security"  # highest — leader in Ledare (§11)
    WARNING = "warning"
    INFO = "info"


class FindingType(enum.StrEnum):
    """FindingType."""

    SECURITY_LEDARE_LEADER = "security_ledare_leader"
    ADULT_IN_SCOUT_UNIT = "adult_in_scout_unit"
    MULTI_AVDELNING = "multi_avdelning"
    YOUNG_LEADER = "young_leader"
    UNDERAGE_IN_LEDARE = "underage_in_ledare"
    NO_AVDELNING = "no_avdelning"
    BAD_PHONE = "bad_phone"
    BAD_EMAIL = "bad_email"


def value_hash(raw: str) -> str:
    """
    Hash of the normalised offending value (§11). An acknowledgement is keyed
    to this, so if the value changes the hash changes and the finding resurfaces.
    A hash is not personal data.
    """
    normalised = "".join(raw.split()).casefold()
    return hashlib.sha256(normalised.encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Finding:
    """Finding."""

    type: FindingType
    severity: Severity
    member_no: str
    # Display fields are live (never persisted); acks store only member_no,
    # type and value_hash (§9, §11).
    member_name: str
    avdelning: str | None
    detail: str
    value_hash: str

    @property
    def ack_key(self) -> tuple[str, str, str]:
        """Ack key."""
        return (self.member_no, str(self.type), self.value_hash)
