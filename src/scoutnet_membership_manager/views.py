"""
Pure read-only view computations shared by the API (Phase 1).

Kept separate from Flask so they are unit-testable without a request context.
"""

from __future__ import annotations

from collections import Counter

from scoutnet_membership_manager.scoutnet.models import MemberList, PaymentBucket

# prev_term is the invoiced term today; current_term is not_invoiced for everyone
# until Höst 2026 is billed (§4). The unpaid view is meaningful against prev_term.
_ACTIONABLE = {PaymentBucket.OUTSTANDING, PaymentBucket.UNKNOWN}


def dues_by_avdelning(memberlist: MemberList) -> list[dict]:
    """
    Per-avdelning payment breakdown, keyed on the invoiced (prev) term, with
    the outstanding members listed for action.
    """
    buckets: dict[str, Counter] = {}
    outstanding: dict[str, list[dict]] = {}
    for m in memberlist.members:
        av = m.unit or "(ingen avdelning)"
        buckets.setdefault(av, Counter())[m.prev_payment().value] += 1
        if m.prev_payment() in _ACTIONABLE:
            outstanding.setdefault(av, []).append(
                {
                    "member_no": m.member_no,
                    "name": m.full_name,
                    "status": m.prev_term_code,
                    "bucket": m.prev_payment().value,
                }
            )
    return [
        {
            "avdelning": av,
            "counts": dict(buckets[av]),
            "outstanding": outstanding.get(av, []),
        }
        for av in sorted(buckets)
    ]
