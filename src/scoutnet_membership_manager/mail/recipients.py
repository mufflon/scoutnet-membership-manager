"""
Resolve mail recipients for a member (§10).

Email both guardians where present, deduplicated case-insensitively in case the
family shares an address. Fall back to the member's own address. If none can be
resolved, return an empty list — the caller surfaces the member as unsendable
rather than failing silently.
"""

from __future__ import annotations

from scoutnet_membership_manager.scoutnet.models import GUARDIAN_EMAIL_FIELDS, Member


def resolve_recipients(member: Member) -> list[str]:
    """Resolve recipients."""
    seen: dict[str, str] = {}
    for f in GUARDIAN_EMAIL_FIELDS:
        v = member.emails.get(f)
        if v:
            seen.setdefault(v.strip().casefold(), v.strip())
    if seen:
        return list(seen.values())
    for f in ("contact_email", "email"):
        v = member.emails.get(f)
        if v:
            return [v.strip()]
    return []
