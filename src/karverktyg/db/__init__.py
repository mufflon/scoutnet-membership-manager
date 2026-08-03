"""
Persistence (CLAUDE.md §9).

Stores the minimum to make workflows resumable and nothing Scoutnet already
holds. Names, addresses, personal numbers, emails and phone numbers are never
written here — they are fetched live and joined at render time. A test asserts
no personal-data column exists.
"""

from karverktyg.db.models import (
    Base,
    CohortTarget,
    EmailTemplate,
    FindingAck,
    MessageLog,
    UppflyttningEntry,
)
from karverktyg.db.session import get_session, make_engine, make_sessionmaker

__all__ = [
    "Base",
    "CohortTarget",
    "EmailTemplate",
    "FindingAck",
    "MessageLog",
    "UppflyttningEntry",
    "get_session",
    "make_engine",
    "make_sessionmaker",
]
