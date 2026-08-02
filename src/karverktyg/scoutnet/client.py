"""Scoutnet clients, constructed per mode (§6).

Only read clients exist in this repo. There is no write method anywhere on
``FixtureClient`` or ``ReadOnlyClient``; the read_write client is Phase 2 and
is deliberately absent, so a bug cannot reach a write path. ``build_client``
refuses ``read_write`` for the same reason.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

from karverktyg.scoutnet.models import MemberList
from karverktyg.scoutnet.parse import parse_memberlist
from karverktyg.settings import Mode, Settings

_VARIANT_PARAMS = {
    "active": {},
    "waiting": {"waiting": "1"},
    "awaiting_approval": {"awaiting_approval": "1"},
}
DEFAULT_FIXTURE = Path("fixtures/memberlist.scrubbed.json")


class ScoutnetError(RuntimeError):
    """A Scoutnet call failed (documented failure modes: 400, 401 — §4)."""


class FixtureClient:
    """Serves committed fixtures. No network, no credentials (§6). Only the
    ``active`` variant is captured so far; other variants return empty."""

    def __init__(self, fixture_path: str | Path = DEFAULT_FIXTURE):
        self._path = Path(fixture_path)
        self._raw: dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8"))

    def memberlist(self, variant: str = "active") -> MemberList:
        if variant not in _VARIANT_PARAMS:
            raise ScoutnetError(f"unknown variant {variant!r}")
        if variant != "active":
            return MemberList(members=[], variant=variant)
        return parse_memberlist(self._raw, "active")

    def organisation_group(self) -> dict[str, Any]:
        """Synthesised aggregate so fixture mode is self-contained and looks
        like read_only to the frontend (§6)."""
        ml = self.memberlist("active")
        n = len(ml)
        return {
            "membercount": n,
            "generated": None,
            "stats": {
                "active": {"value": n, "term_label": ml.current_term_label},
            },
            "_synthesised": True,
        }

    def close(self) -> None:  # symmetry with ReadOnlyClient
        pass


class ReadOnlyClient:
    """Live read-only access to Scoutnet. HTTP Basic, per-endpoint key (§4)."""

    def __init__(self, settings: Settings):
        self._entity_id = settings.entity_id or ""
        self._memberlist_key = settings.memberlist_key
        self._org_key = settings.organisation_group_key
        self._http = httpx.Client(
            base_url=settings.base_url.rstrip("/"),
            timeout=settings.http_timeout_s,
            headers={"Accept": "application/json"},
        )

    @retry(
        retry=retry_if_exception_type(httpx.TransportError),
        stop=stop_after_attempt(3),
        wait=wait_fixed(1),
        reraise=True,
    )
    def _get(self, path: str, key: Any, params: dict[str, str]) -> dict[str, Any]:
        if key is None:
            raise ScoutnetError(f"no API key configured for {path}")
        resp = self._http.get(path, params=params, auth=(self._entity_id, key.get_secret_value()))
        if resp.status_code == 401:
            raise ScoutnetError(
                f"401 Unauthorized for {path} — check entity id and that the key "
                "is the one for this endpoint"
            )
        if resp.status_code == 400:
            raise ScoutnetError(f"400 Bad Request for {path}: {resp.text[:200]}")
        resp.raise_for_status()
        return resp.json()

    def memberlist(self, variant: str = "active") -> MemberList:
        if variant not in _VARIANT_PARAMS:
            raise ScoutnetError(f"unknown variant {variant!r}")
        raw = self._get("/group/memberlist", self._memberlist_key, _VARIANT_PARAMS[variant])
        return parse_memberlist(raw, variant)

    def organisation_group(self) -> dict[str, Any]:
        return self._get("/organisation/group", self._org_key, {})

    def close(self) -> None:
        self._http.close()


def build_client(settings: Settings) -> FixtureClient | ReadOnlyClient:
    if settings.mode is Mode.FIXTURE:
        return FixtureClient()
    if settings.mode is Mode.READ_ONLY:
        settings.require_live_credentials()
        return ReadOnlyClient(settings)
    raise NotImplementedError(
        "read_write client is Phase 2; no write code exists in this repo (§6, §7)"
    )
