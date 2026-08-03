# Reproducible build with docker buildx (§14). Multi-stage: uv builds the venv,
# the runtime image carries only the venv + app. Distribution target is unsolved
# (§14) — this stays registry-agnostic.
FROM python:3.14-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependency layer (cached unless the lock changes).
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev

# App layer.
COPY src ./src
COPY config ./config
COPY fixtures ./fixtures
COPY migrations ./migrations
COPY vendor ./vendor
COPY alembic.ini ./
RUN uv sync --frozen --no-dev


FROM python:3.14-slim AS runtime
WORKDIR /app
# Non-root.
RUN useradd --uid 10001 --create-home app
COPY --from=build --chown=app:app /app /app
ENV PATH="/app/.venv/bin:$PATH" \
    SCOUTNET_MODE=read_only \
    PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
# Frontend and API share one image/container (simple; the static frontend is
# tiny and served by Flask). readiness = /readyz (Postgres only), liveness /healthz.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60", \
     "karverktyg.wsgi:app"]
