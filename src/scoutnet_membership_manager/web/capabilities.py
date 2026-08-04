"""Capabilities page data (CLAUDE.md §12): what this deployment can do."""

from __future__ import annotations

import json
from pathlib import Path

from scoutnet_membership_manager.collation import using_icu
from scoutnet_membership_manager.config.models import KarConfig
from scoutnet_membership_manager.settings import Mode, Settings

_VENDOR_META = Path("vendor/openapi/meta.json")


def _openapi_meta() -> dict | None:
    if _VENDOR_META.exists():
        try:
            return json.loads(_VENDOR_META.read_text("utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def capabilities(settings: Settings, config: KarConfig) -> dict:
    """Capabilities."""
    fingerprints = settings.endpoint_key_fingerprints()
    endpoints = [
        {"endpoint": ep, "configured": h is not None, "key_hash": h}
        for ep, h in fingerprints.items()
    ]
    # Read actions work in fixture and read_only. Writing needs read_write mode
    # AND the per-endpoint write key present (§6, §12).
    write_key_present = fingerprints.get("organisation/update/membership") is not None
    if settings.mode is Mode.READ_WRITE and write_key_present:
        execute_writes = {"action": "execute_writes", "enabled": True, "reason": None}
    elif settings.mode is Mode.READ_WRITE:
        execute_writes = {
            "action": "execute_writes",
            "enabled": False,
            "reason": "read_write mode is active but no update/membership key is configured",
        }
    else:
        execute_writes = {
            "action": "execute_writes",
            "enabled": False,
            "reason": f"requires read_write mode (current mode: {settings.mode.value})",
        }
    actions = [
        {"action": "view_dues", "enabled": True, "reason": None},
        {"action": "view_findings", "enabled": True, "reason": None},
        {"action": "compute_uppflyttning", "enabled": True, "reason": None},
        {"action": "export_changelist", "enabled": True, "reason": None},
        execute_writes,
    ]
    return {
        "app_version": settings.app_version,
        "build_number": settings.build_number,
        "kar": settings.kar_name,
        "mode": settings.mode.value,
        "read_write_active": settings.mode is Mode.READ_WRITE,
        "endpoints": endpoints,
        "actions": actions,
        "icu_collation": using_icu(),
        "config_placeholder": not config.avdelningar,
        "openapi": _openapi_meta(),
    }
