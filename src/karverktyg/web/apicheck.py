"""
API-check: probe each Scoutnet endpoint key with a real read (§12).

Each per-endpoint key (§4) is exercised independently so a green result means
that key actually authorises that endpoint right now — not merely that it is
present. In fixture mode no network call is made: the committed sample data is
served, every check is green, and the report says loudly that it is fixtures.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import httpx

from karverktyg.scoutnet.client import ScoutnetError
from karverktyg.settings import FINGERPRINT_ALGO, FINGERPRINT_CHARS, Mode, Settings

if TYPE_CHECKING:
    from karverktyg.scoutnet.client import FixtureClient, ReadOnlyClient

# Documented probe failure modes (§4): our own error + any httpx failure.
_PROBE_ERRORS = (ScoutnetError, httpx.HTTPError)


def _members_detail(client: FixtureClient | ReadOnlyClient) -> str:
    ml = client.memberlist("active")
    return f"{len(ml)} medlemmar i aktiv lista"


def _org_detail(client: FixtureClient | ReadOnlyClient) -> str:
    data = client.organisation_group()
    if isinstance(data, dict) and data.get("membercount") is not None:
        return f"svarade (membercount={data['membercount']})"
    n = len(data) if hasattr(data, "__len__") else "?"
    return f"svarade ({n} fält)"


def api_check(settings: Settings, client: FixtureClient | ReadOnlyClient) -> dict:
    """Probe every endpoint key with a real read; green when nothing fails."""
    is_fixture = settings.mode is Mode.FIXTURE
    fingerprints = settings.endpoint_key_fingerprints()
    probes: list[tuple[str, str, object, Callable[[], str]]] = [
        (
            "group/memberlist",
            "SCOUTNET_MEMBERLIST_KEY",
            settings.memberlist_key,
            lambda: _members_detail(client),
        ),
        (
            "organisation/group",
            "SCOUTNET_ORGANISATION_GROUP_KEY",
            settings.organisation_group_key,
            lambda: _org_detail(client),
        ),
    ]

    checks: list[dict] = []
    for endpoint, env, key, probe in probes:
        row = {"endpoint": endpoint, "key_env": env, "key_hash": fingerprints.get(endpoint)}
        if is_fixture:
            # No credentials, no network — the committed fixture stands in.
            row.update(configured=False, status="fixture", detail=_safe(probe))
        elif key is None:
            # Blank key = endpoint deliberately disabled; not a failure.
            row.update(
                configured=False,
                status="disabled",
                detail="nyckel ej konfigurerad – endpoint avstängd",
            )
        else:
            row.update(configured=True, **_run(probe))
        checks.append(row)

    # The write key is *listed* but never auto-tested: exercising it means a real
    # write, which means fabricating a member number (hard rule 6). Its presence
    # and fingerprint are shown; verification is manual (Verifiera skrivning, §8).
    write_key = settings.update_membership_key
    write_row = {
        "endpoint": "organisation/update/membership",
        "key_env": "SCOUTNET_UPDATE_MEMBERSHIP_KEY",
        "key_hash": fingerprints.get("organisation/update/membership"),
    }
    if is_fixture:
        write_row.update(
            configured=False, status="untested", detail="fixturläge – skrivningar testas aldrig"
        )
    elif write_key is None:
        write_row.update(
            configured=False,
            status="disabled",
            detail="nyckel ej konfigurerad – skrivning avstängd",
        )
    else:
        write_row.update(
            configured=True,
            status="untested",
            detail="nyckel konfigurerad – skrivningar testas aldrig automatiskt. "
            "Verifiera manuellt via fliken Verifiera skrivning.",
        )
    checks.append(write_row)

    return {
        "mode": settings.mode.value,
        "fixture": is_fixture,
        "all_ok": all(c["status"] != "fail" for c in checks),
        "checks": checks,
        # How the fingerprint column is computed, so it can be reproduced.
        "fingerprint": {"algo": FINGERPRINT_ALGO, "chars": FINGERPRINT_CHARS, "over": "utf-8"},
    }


def _run(probe: Callable[[], str]) -> dict:
    try:
        return {"status": "ok", "detail": probe()}
    except _PROBE_ERRORS as e:
        return {"status": "fail", "detail": str(e)}


def _safe(probe: Callable[[], str]) -> str:
    try:
        return probe()
    except _PROBE_ERRORS as e:  # a broken fixture shouldn't 500 the page
        return f"fixturfel: {e}"
