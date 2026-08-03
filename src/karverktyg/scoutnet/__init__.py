"""
Scoutnet API client and models (CLAUDE.md §4).

The client is constructed per mode (§6); the write method exists only on the
read_write client, never on the read-only or fixture clients, so in those modes
a bug cannot reach a write path.
"""

from karverktyg.scoutnet.client import (
    FixtureClient,
    ReadOnlyClient,
    ReadWriteClient,
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
    "ReadWriteClient",
    "Role",
    "ScoutnetError",
    "build_client",
    "parse_memberlist",
]
