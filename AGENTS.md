# Agent guide

If you are an AI assistant working in this repo, read these first, in order:

1. **`CLAUDE.md`** — the authoritative, spec-grade description of the whole
   system. The code references it as `§N` (e.g. `§17` is the uppflyttning engine,
   `§13` is configuration, `§8`/`§9` the write path and no-personal-data rule).
   When behaviour and CLAUDE.md disagree, treat CLAUDE.md as intent and reconcile.
2. **`docs/INTRO.md`** — the same system in one page (modes, config model, the
   uppflyttning routing rule).
3. **`README.md`** — setup, deploy, and the configuration reference.

## Working here

- **Language & tooling:** Python 3.14, `uv`, Flask, pydantic(-settings),
  SQLAlchemy, openpyxl. Lint/format with `ruff`; tests with `pytest`. Everything
  runs offline — `uv run pytest && uv run ruff check . && uv run ruff format --check .`.
- **Hard rules (see CLAUDE.md):** never commit API keys or real member data; the
  committed fixture is fabricated (`scripts/make_fixture.py`); snapshots and the DB
  store no personal data.
- **Docstrings carry the rationale** (with `§` references) — keep that style; it is
  how the code stays understandable.
- **Config is small and optional:** brackets are national code, a kår's config is
  just its avdelningar; the app runs with no config by inferring from the data.
  If you change what is configurable, update `scripts/make_config.py`,
  `docs/scoutnet-membership-manager.schema.json` (there is a sync test), and CLAUDE.md §13 together.
