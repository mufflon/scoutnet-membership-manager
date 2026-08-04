# Reproducible build with docker buildx (§14). Multi-stage: uv builds the venv,
# the runtime image carries only the venv + app. Distribution target is unsolved
# (§14) — this stays registry-agnostic.
FROM python:3.14-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.12.1 /uv /bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependency layer (cached unless the lock changes). The [pdf] extra pulls in
# WeasyPrint for A4 PDF report rendering (§19); its native libs are installed in
# the runtime stage below.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --no-dev --extra pdf

# App layer.
COPY src ./src
COPY docs ./docs
COPY karverktyg.json ./
COPY fixtures ./fixtures
COPY migrations ./migrations
COPY vendor ./vendor
COPY alembic.ini ./
RUN uv sync --frozen --no-dev --extra pdf


FROM python:3.14-slim AS runtime
WORKDIR /app
# WeasyPrint (the [pdf] extra) renders the A4 PDF reports (§19) and needs these
# native libraries at runtime — pango/cairo/gobject pull in via libpango, plus
# DejaVu fonts for the report typeface and gdk-pixbuf for the kår logo. Without
# them the PDF endpoints degrade to a clear "install the [pdf] extra" 503; the
# rest of the app is unaffected.
RUN apt-get update && apt-get install --no-install-recommends -y \
      libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf-2.0-0 libffi8 \
      fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
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
# Threaded workers: the work is I/O-bound (blocking on slow Scoutnet reads —
# organisation/group and awaiting_approval can take ~30 s), so gthread with many
# threads gives ample concurrency without one slow read starving the rest. The
# 120 s timeout leaves headroom above a first (uncached) slow read.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", \
     "--worker-class", "gthread", "--workers", "4", "--threads", "8", \
     "--timeout", "120", "--graceful-timeout", "30", \
     "karverktyg.wsgi:app"]
