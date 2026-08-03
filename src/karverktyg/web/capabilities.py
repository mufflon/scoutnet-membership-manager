"""Capabilities page data (CLAUDE.md §12): what this deployment can do."""

from __future__ import annotations

import json
from pathlib import Path

from karverktyg.collation import using_icu
from karverktyg.config.models import KarConfig
from karverktyg.settings import Mode, Settings

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
    # Read actions work in fixture and read_only; writes are Phase 2 (absent).
    actions = [
        {"action": "view_dues", "enabled": True, "reason": None},
        {"action": "view_findings", "enabled": True, "reason": None},
        {"action": "compute_uppflyttning", "enabled": True, "reason": None},
        {"action": "export_changelist", "enabled": True, "reason": None},
        {
            "action": "execute_writes",
            "enabled": False,
            "reason": "read_write mode is not available in Phase 1 (§7)",
        },
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
        "config_placeholder": config.placeholder,
        "openapi": _openapi_meta(),
    }
