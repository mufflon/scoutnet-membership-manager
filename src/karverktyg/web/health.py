"""Health and readiness probes (CLAUDE.md §14).

Liveness is a cheap local check. Readiness additionally verifies Postgres
connectivity and must NOT call Scoutnet — an upstream outage must not cycle pods.
Scoutnet reachability belongs on the capabilities page, not in a probe.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

health_bp = Blueprint("health", __name__)


@health_bp.get("/healthz")
def healthz():
    return jsonify(status="ok"), 200


@health_bp.get("/readyz")
def readyz():
    engine = current_app.config["ENGINE"]
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as e:  # noqa: BLE001 - report any DB failure as not-ready
        return jsonify(status="not_ready", database=str(e)[:120]), 503
    return jsonify(status="ready"), 200
