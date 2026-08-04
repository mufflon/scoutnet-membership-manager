"""
Read-only canary (§14).

Seasonal software — uppflyttning runs once a year — so the point is to discover
breakage in April rather than on the day two hundred scouts need moving. Fetches
the memberlist and organisation/group and asserts the basics. Must run in
read_only (or fixture); never writes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from scoutnet_membership_manager.scoutnet.client import ScoutnetError, build_client
from scoutnet_membership_manager.settings import Settings

MIN_MEMBERS = 50


@dataclass
class CanaryResult:
    """CanaryResult."""

    ok: bool
    member_count: int | None = None
    checks: list[tuple[str, bool, str]] = field(default_factory=list)

    def render(self) -> str:
        """Render."""
        head = f"Canary: {'OK' if self.ok else 'FAIL'} (members={self.member_count})"
        body = "\n".join(
            f"  [{'x' if p else ' '}] {name}: {detail}" for name, p, detail in self.checks
        )
        return f"{head}\n{body}"


def run_canary(settings: Settings, min_members: int = MIN_MEMBERS) -> CanaryResult:
    """Run canary."""
    checks: list[tuple[str, bool, str]] = []
    client = build_client(settings)

    try:
        ml = client.memberlist()
    except ScoutnetError as e:
        checks.append(("memberlist_call", False, str(e)))
        return CanaryResult(ok=False, checks=checks)
    checks.append(("memberlist_call", True, "ok"))
    checks.append(("parses", True, f"{len(ml)} members"))

    n = len(ml)
    checks.append(("member_count", n >= min_members, f"{n} >= {min_members}"))
    fields_ok = bool(ml.members) and bool(ml.members[0].member_no) and bool(ml.current_term_label)
    checks.append(("expected_fields", fields_ok, "member_no + current_term present"))

    try:
        client.organisation_group()
        checks.append(("organisation_group", True, "ok"))
    except ScoutnetError as e:
        checks.append(("organisation_group", False, str(e)))

    ok = all(p for _, p, _ in checks)
    return CanaryResult(ok=ok, member_count=n, checks=checks)
