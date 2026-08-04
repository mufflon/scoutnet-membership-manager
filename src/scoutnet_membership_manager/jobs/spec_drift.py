"""
OpenAPI spec drift detection (§14).

Reports the vendored version and compares it against upstream. Full detection
re-bundles the upstream document with `npx @redocly/cli bundle` and diffs paths
and fields against vendor/openapi/; that runs in CI/CronJob with network + node.
This never auto-updates the vendored copy — adopting a new spec is a reviewed
change. The result is surfaced on the capabilities page so drift is visible.
"""

from __future__ import annotations

import contextlib
import json
from dataclasses import dataclass
from pathlib import Path

VENDOR_META = Path("vendor/openapi/meta.json")
_NPM_LATEST = "https://registry.npmjs.org/@scouterna/scoutnet-openapi/latest"


@dataclass
class DriftResult:
    """DriftResult."""

    vendored_version: str | None
    upstream_version: str | None
    drifted: bool | None  # None = upstream not checked
    note: str

    def render(self) -> str:
        """Render."""
        up = self.upstream_version or "(not checked)"
        state = "DRIFT" if self.drifted else ("in sync" if self.drifted is False else "unknown")
        return (
            f"Spec drift: {state}\n  vendored: {self.vendored_version}\n"
            f"  upstream: {up}\n  {self.note}"
        )


def _fetch_upstream_version(timeout: float = 10.0) -> str | None:
    try:
        import httpx

        r = httpx.get(_NPM_LATEST, timeout=timeout)
        r.raise_for_status()
        return r.json().get("version")
    except Exception:  # noqa: BLE001 - drift check must never crash the run
        return None


def run_drift_check(vendor_meta: Path = VENDOR_META, *, check_upstream: bool = True) -> DriftResult:
    """Run drift check."""
    vendored = None
    if vendor_meta.exists():
        with contextlib.suppress(json.JSONDecodeError):
            vendored = json.loads(vendor_meta.read_text("utf-8")).get("version")
    upstream = _fetch_upstream_version() if check_upstream else None
    drifted = None if upstream is None else (upstream != vendored)
    note = (
        "Full path/field diff requires re-bundling upstream with redocly (§14). "
        "Never auto-updates the vendored copy."
    )
    return DriftResult(
        vendored_version=vendored, upstream_version=upstream, drifted=drifted, note=note
    )
