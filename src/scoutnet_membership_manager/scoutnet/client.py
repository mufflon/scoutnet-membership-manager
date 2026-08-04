"""
Scoutnet clients, constructed per mode (§6).

The mode gate is enforced at construction: ``FixtureClient`` and
``ReadOnlyClient`` have no write method anywhere, so in ``fixture`` / ``read_only``
a bug cannot reach a write path. The single write method lives only on
``ReadWriteClient``, which ``build_client`` returns only for ``read_write`` mode
and only once the per-endpoint write key is present.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from scoutnet_membership_manager.scoutnet.models import MemberList, PaymentBucket
from scoutnet_membership_manager.scoutnet.parse import parse_memberlist
from scoutnet_membership_manager.settings import Mode, Settings

_VARIANT_PARAMS = {
    "active": {},
    "waiting": {"waiting": "1"},
    "awaiting_approval": {"awaiting_approval": "1"},
}
DEFAULT_FIXTURE = Path("fixtures/memberlist.demo.json")
# Synthetic sample so the membership-draft feature is demoable before a real
# waiting/awaiting capture exists. Fully fabricated.
_WAITING_SAMPLE = Path("fixtures/memberlist-waiting.sample.json")


_HTTP_OK = 200
_HTTP_UNAUTHORIZED = 401
_HTTP_BAD_REQUEST = 400

# Short cache so navigating between blades doesn't re-fetch the (multi-second)
# memberlist each time. Read-only data that changes slowly; the operator can
# always reload for fresh data.
_MEMBERLIST_TTL_S = 90.0
# organisation/group is aggregate data that changes slowly and (for some kårer)
# answers very slowly — cache a success so a blade needing it pays the cost at
# most once per window, not on every load (§4, §20 reconciliation).
_ORG_TTL_S = 300.0
# Negative cache: a variant that read-times-out (awaiting_approval reliably does
# for this kår, §4) fast-fails for a short window instead of re-blocking a worker
# for the full timeout on every request. The operator reloads for fresh data.
_NEG_TTL_S = 120.0
# For the fixture aggregate's synthesised below_26: the committed capture is the
# 2026 season, so members born after 2000 are under 26. Fixtures only (§6).
_FIXTURE_BORN_UNDER_26 = 2000


class ScoutnetError(RuntimeError):
    """
    A Scoutnet call failed (documented failure modes: 400, 401 — §4).

    Carries the HTTP status and response body when available, so a write caller
    can surface a 400's per-member error strings without re-parsing a message
    string (§8 error handling).
    """

    def __init__(
        self, message: str, *, status_code: int | None = None, body: str | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class FixtureClient:
    """
    Serves committed fixtures. No network, no credentials (§6). Only the
    ``active`` variant is captured so far; other variants return empty.
    """

    def __init__(self, fixture_path: str | Path = DEFAULT_FIXTURE) -> None:
        self._path = Path(fixture_path)
        self._raw: dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8"))

    def memberlist(self, variant: str = "active") -> MemberList:
        """Load a memberlist variant from the committed/synthetic fixtures."""
        if variant not in _VARIANT_PARAMS:
            raise ScoutnetError(f"unknown variant {variant!r}")
        if variant == "active":
            return parse_memberlist(self._raw, "active")
        # waiting / awaiting_approval: serve the synthetic sample if present.
        if _WAITING_SAMPLE.exists():
            raw = json.loads(_WAITING_SAMPLE.read_text(encoding="utf-8"))
            return parse_memberlist(raw, variant)
        return MemberList(members=[], variant=variant)

    def organisation_group(self) -> dict[str, Any]:
        """
        Synthesised aggregate so fixture mode is self-contained and looks like
        read_only to the frontend (§6). Derived from the committed memberlist so
        the Översikt cross-checks (§20) have real figures to agree with.
        """
        ml = self.memberlist("active")
        n = len(ml)
        troops = {m.unit for m in ml.members if m.unit}
        rolecount = sum(len(m.roles) for m in ml.members)
        paid_prev = sum(1 for m in ml.members if m.prev_payment() is PaymentBucket.SETTLED)
        below_26 = sum(
            1 for m in ml.members if m.birth_year and m.birth_year > _FIXTURE_BORN_UNDER_26
        )
        try:
            waitingcount = len(self.memberlist("waiting"))
        except ScoutnetError:
            waitingcount = 0
        return {
            "membercount": n,
            "rolecount": rolecount,
            "waitingcount": waitingcount,
            "active_troops": len(troops),
            "generated": None,
            "stats": {
                "active": {"value": n, "term_label": ml.current_term_label},
                "active_paid_previous": {"value": paid_prev, "term_label": ml.prev_term_label},
                "below_26": {"value": below_26},
            },
            "_synthesised": True,
        }

    def close(self) -> None:
        """No-op; present for symmetry with ReadOnlyClient."""


class ReadOnlyClient:
    """Live read-only access to Scoutnet. HTTP Basic, per-endpoint key (§4)."""

    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None) -> None:
        self._entity_id = settings.entity_id or ""
        self._memberlist_key = settings.memberlist_key
        self._org_key = settings.organisation_group_key
        self._cache: dict[str, tuple[float, MemberList]] = {}
        self._org_cache: tuple[float, dict[str, Any]] | None = None
        self._neg_cache: dict[str, float] = {}  # variant -> monotonic ts of a read timeout
        # ``transport`` is a test seam (httpx.MockTransport); None in production.
        self._http = httpx.Client(
            base_url=settings.base_url.rstrip("/"),
            timeout=settings.http_timeout_s,
            headers={"Accept": "application/json"},
            transport=transport,
        )

    # Retry only when the connection itself fails; a read timeout means the
    # server accepted but is slow, so retrying just multiplies the wait (§4).
    @retry(
        retry=retry_if_exception_type((httpx.ConnectError, httpx.ConnectTimeout)),
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        reraise=True,
    )
    def _get(self, path: str, key: Any, params: dict[str, str]) -> dict[str, Any]:
        if key is None:
            raise ScoutnetError(f"no API key configured for {path}")
        resp = self._http.get(path, params=params, auth=(self._entity_id, key.get_secret_value()))
        if resp.status_code == _HTTP_UNAUTHORIZED:
            raise ScoutnetError(
                f"401 Unauthorized for {path} — check entity id and that the key "
                "is the one for this endpoint"
            )
        if resp.status_code == _HTTP_BAD_REQUEST:
            raise ScoutnetError(f"400 Bad Request for {path}: {resp.text[:200]}")
        resp.raise_for_status()
        return resp.json()

    def memberlist(self, variant: str = "active", *, fresh: bool = False) -> MemberList:
        """
        Fetch a live memberlist variant, served from a short TTL cache (§4).

        ``fresh=True`` bypasses the cache — used by the write executor for the
        per-chunk status re-read and post-run reconciliation, which must see
        current data, not a value cached up to 90 s ago (§8).
        """
        if variant not in _VARIANT_PARAMS:
            raise ScoutnetError(f"unknown variant {variant!r}")
        now = time.monotonic()
        if not fresh:
            cached = self._cache.get(variant)
            if cached is not None and now - cached[0] < _MEMBERLIST_TTL_S:
                return cached[1]
            neg = self._neg_cache.get(variant)
            if neg is not None and now - neg < _NEG_TTL_S:
                raise ScoutnetError(
                    f"{variant} nådde tidsgräns nyligen; cachas som otillgänglig "
                    f"i {_NEG_TTL_S:.0f}s (ladda om för nytt försök)"
                )
        try:
            raw = self._get("/group/memberlist", self._memberlist_key, _VARIANT_PARAMS[variant])
        except httpx.TimeoutException:
            # A read timeout means Scoutnet accepted but is slow (§4). Remember it
            # so we don't tie up a worker for the full timeout on every request.
            self._neg_cache[variant] = now
            raise
        ml = parse_memberlist(raw, variant)
        self._cache[variant] = (now, ml)
        self._neg_cache.pop(variant, None)
        return ml

    def organisation_group(self) -> dict[str, Any]:
        """Fetch the aggregate organisation/group stats (§4), cached (slow endpoint)."""
        now = time.monotonic()
        if self._org_cache is not None and now - self._org_cache[0] < _ORG_TTL_S:
            return self._org_cache[1]
        data = self._get("/organisation/group", self._org_key, {})
        self._org_cache = (now, data)
        return data

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()


class ReadWriteClient(ReadOnlyClient):
    """
    Live read *and* write access (§6). The only client carrying a write method;
    constructed only for ``read_write`` mode, so a bug elsewhere cannot reach a
    write path (the read clients have no such method at all).

    The write is deliberately **not** retried. Unlike a read, where a connection
    failure is safe to retry, a write that fails for any reason stops the run and
    is surfaced to the operator, never retried automatically (§8).
    """

    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None) -> None:
        super().__init__(settings, transport=transport)
        self._write_key = settings.update_membership_key

    def update_membership(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        POST a membership-update batch (§4). ``payload`` is keyed by member
        number; each entry carries the required ``status`` plus the fields to
        change. Returns the parsed 200 body; raises ``ScoutnetError`` on any
        non-200 (400 bodies carry per-member error strings). Never retried.
        """
        if self._write_key is None:
            raise ScoutnetError("no API key configured for /organisation/update/membership")
        resp = self._http.post(
            "/organisation/update/membership",
            json=payload,
            auth=(self._entity_id, self._write_key.get_secret_value()),
        )
        if resp.status_code != _HTTP_OK:
            body = resp.text[:2000]
            raise ScoutnetError(
                f"{resp.status_code} from /organisation/update/membership: {body}",
                status_code=resp.status_code,
                body=body,
            )
        try:
            return resp.json()
        except ValueError as e:  # a 200 with an unparseable body is a failed chunk
            raise ScoutnetError(
                "malformed 200 body from /organisation/update/membership",
                status_code=_HTTP_OK,
                body=resp.text[:2000],
            ) from e


def build_client(settings: Settings) -> FixtureClient | ReadOnlyClient | ReadWriteClient:
    """
    Construct the client for the active mode (§6).

    The mode gate lives here: the write method exists only on the ``read_write``
    client object.
    """
    if settings.mode is Mode.FIXTURE:
        return FixtureClient()
    if settings.mode is Mode.READ_ONLY:
        settings.require_live_credentials()
        return ReadOnlyClient(settings)
    settings.require_live_credentials()  # also requires the write key for read_write
    return ReadWriteClient(settings)
