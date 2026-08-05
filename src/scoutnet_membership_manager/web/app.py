"""Flask application factory (§3, §6)."""

from __future__ import annotations

from pathlib import Path

import httpx
from flask import Flask, jsonify
from flask.typing import ResponseReturnValue
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from scoutnet_membership_manager.db.models import Base
from scoutnet_membership_manager.db.session import make_engine, make_sessionmaker
from scoutnet_membership_manager.scoutnet.client import ScoutnetError, build_client
from scoutnet_membership_manager.settings import Mode, Settings
from scoutnet_membership_manager.uppflyttning.cohort import CohortYearConflict
from scoutnet_membership_manager.web.api import api_bp
from scoutnet_membership_manager.web.health import health_bp
from scoutnet_membership_manager.web.runs import RunBusy, RunManager
from scoutnet_membership_manager.web.writes import writes_bp
from scoutnet_membership_manager.write.executor import AllowlistViolation, ExecutorError

_STATIC = Path(__file__).parent / "static"


_DEFAULT_DB = "postgresql+psycopg://localhost/scoutnet_membership_manager"


def _build_engine(settings: Settings) -> Engine:
    """
    Build the DB engine for the mode.

    Fixture mode with no database_url runs on an ephemeral in-memory SQLite so
    the app needs no infrastructure (§6). Give fixture mode a real database_url
    (e.g. Postgres) and its workflow state persists — the schema is created
    directly since migrations are a live-mode concern. Live modes use the
    configured database, whose schema comes from alembic migrations.
    """
    url = settings.database_url
    is_sqlite = not url or url.startswith("sqlite")
    # Fixture mode, or any mode pointed at sqlite (dev/tests), creates the schema
    # directly rather than via migrations. Only sqlite gets the in-process
    # StaticPool / check_same_thread args — a real DB (e.g. fixture mode on the
    # in-cluster Postgres) must use the normal engine, or psycopg rejects them.
    if settings.mode is Mode.FIXTURE or is_sqlite:
        if is_sqlite:
            engine = create_engine(
                url or "sqlite://",
                future=True,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        else:
            engine = make_engine(url)
        Base.metadata.create_all(engine)
        return engine
    return make_engine(url or _DEFAULT_DB)


def create_app(settings: Settings | None = None, *, client: object | None = None) -> Flask:
    """
    Build the Flask app: API, static frontend, health probes (§6).

    ``client`` overrides the Scoutnet client — a test seam for injecting a mock
    read_write client. In production it is None and ``build_client`` constructs
    the mode-appropriate client, failing loudly if a live deployment lacks keys.
    """
    settings = settings or Settings()
    kar_config = settings.kar  # from scoutnet-membership-manager.json (§13); empty => inferred

    app = Flask(__name__, static_folder=str(_STATIC), static_url_path="")
    app.config.update(
        SETTINGS=settings,
        KAR_CONFIG=kar_config,
        SCOUTNET=client if client is not None else build_client(settings),
        ENGINE=_build_engine(settings),
        RUN_MANAGER=RunManager(),
    )
    app.config["SESSIONMAKER"] = make_sessionmaker(app.config["ENGINE"])

    app.register_blueprint(api_bp)
    app.register_blueprint(writes_bp)
    app.register_blueprint(health_bp)

    @app.get("/")
    def index() -> ResponseReturnValue:
        return app.send_static_file("index.html")

    @app.errorhandler(ScoutnetError)
    def _scoutnet_error(e: ScoutnetError) -> ResponseReturnValue:
        return jsonify(error=str(e)), 502

    @app.errorhandler(httpx.TimeoutException)
    def _scoutnet_timeout(_e: httpx.TimeoutException) -> ResponseReturnValue:
        # A Scoutnet read exceeded http_timeout_s — intermittent upstream slowness,
        # not a client error. Return a clear, retryable message instead of a bare
        # 500 the browser surfaces as "Load failed". The read endpoints in api.py
        # already swallow httpx.HTTPError; this covers the write/preview paths
        # (e.g. the fresh dry-run read) that let the timeout propagate.
        return jsonify(error="Scoutnet svarade inte i tid. Ladda om och försök igen."), 504

    @app.errorhandler(CohortYearConflict)
    def _cohort_conflict(e: CohortYearConflict) -> ResponseReturnValue:
        return jsonify(error=str(e)), 409

    @app.errorhandler(AllowlistViolation)
    def _allowlist(e: AllowlistViolation) -> ResponseReturnValue:
        return jsonify(error=str(e)), 400

    @app.errorhandler(RunBusy)
    def _run_busy(e: RunBusy) -> ResponseReturnValue:
        return jsonify(error=str(e)), 409

    @app.errorhandler(ExecutorError)
    def _executor_error(e: ExecutorError) -> ResponseReturnValue:
        return jsonify(error=str(e)), 400

    return app
