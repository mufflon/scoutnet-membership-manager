"""
Scoutnet API client and models (CLAUDE.md §4).

Read-only in Phase 1. The client is constructed per mode (§6); write methods do
not exist on the read-only or fixture clients, so a bug cannot reach them.
"""

from karverktyg.scoutnet.client import (
    FixtureClient,
    ReadOnlyClient,
    ScoutnetError,
    build_client,
)
from karverktyg.scoutnet.models import (
    Member,
    MemberList,
    PaymentBucket,
    Role,
)
from karverktyg.scoutnet.parse import parse_memberlist

__all__ = [
    "FixtureClient",
    "Member",
    "MemberList",
    "PaymentBucket",
    "ReadOnlyClient",
    "Role",
    "ScoutnetError",
    "build_client",
    "parse_memberlist",
]
