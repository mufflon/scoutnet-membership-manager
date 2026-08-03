"""Pure read-only view computations shared by the API (Phase 1).

Kept separate from Flask so they are unit-testable without a request context.
"""

from __future__ import annotations

from collections import Counter

from karverktyg.scoutnet.models import MemberList, PaymentBucket
from karverktyg.settings import Settings

# prev_term is the invoiced term today; current_term is not_invoiced for everyone
# until Höst 2026 is billed (§4). The unpaid view is meaningful against prev_term.
_ACTIONABLE = {PaymentBucket.OUTSTANDING, PaymentBucket.UNKNOWN}


def overview(memberlist: MemberList, settings: Settings) -> dict:
    return {
        "kar": settings.kar_name,
        "member_count": len(memberlist),
        "current_term": memberlist.current_term_label,
        "prev_term": memberlist.prev_term_label,
        "avdelning_count": len({m.unit for m in memberlist.members if m.unit}),
        "note_current_term": "Höst-terminen är ännu inte fakturerad – "
        "betalvyn gäller föregående termin.",
    }


def dues_by_avdelning(memberlist: MemberList) -> list[dict]:
    """Per-avdelning payment breakdown, keyed on the invoiced (prev) term, with
    the outstanding members listed for action."""
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
