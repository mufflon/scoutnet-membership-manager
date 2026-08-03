"""Flask application factory (§3, §6)."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify
from flask.typing import ResponseReturnValue
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from karverktyg.config import load_config
from karverktyg.db.models import Base
from karverktyg.db.session import make_engine, make_sessionmaker
from karverktyg.scoutnet.client import ScoutnetError, build_client
from karverktyg.settings import Mode, Settings
from karverktyg.uppflyttning.cohort import CohortYearConflict
from karverktyg.web.api import api_bp
from karverktyg.web.health import health_bp

_STATIC = Path(__file__).parent / "static"


def _build_engine(settings: Settings) -> Engine:
    """
    Fixture mode gets a self-contained in-memory SQLite with the schema
    created, so the full app runs with no infrastructure (§6). Live modes use
    the configured database, whose schema comes from alembic migrations.
    """
    if settings.mode is Mode.FIXTURE:
        engine = create_engine(
            "sqlite://",
            future=True,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        return engine
    return make_engine(settings.database_url)


def create_app(settings: Settings | None = None) -> Flask:
    """Build the Flask app: read-only API, static frontend, health probes (§6)."""
    settings = settings or Settings()
    kar_config = load_config(settings.config_path)

    app = Flask(__name__, static_folder=str(_STATIC), static_url_path="")
    app.config.update(
        SETTINGS=settings,
        KAR_CONFIG=kar_config,
        # build_client enforces the mode (§6): read clients only, and it fails
        # loudly here if a read_only/read_write deployment lacks its keys.
        SCOUTNET=build_client(settings),
        ENGINE=_build_engine(settings),
    )
    app.config["SESSIONMAKER"] = make_sessionmaker(app.config["ENGINE"])

    app.register_blueprint(api_bp)
    app.register_blueprint(health_bp)

    @app.get("/")
    def index() -> ResponseReturnValue:
        return app.send_static_file("index.html")

    @app.errorhandler(ScoutnetError)
    def _scoutnet_error(e: ScoutnetError) -> ResponseReturnValue:
        return jsonify(error=str(e)), 502

    @app.errorhandler(CohortYearConflict)
    def _cohort_conflict(e: CohortYearConflict) -> ResponseReturnValue:
        return jsonify(error=str(e)), 409

    return app
