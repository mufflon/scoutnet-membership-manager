"""Alembic environment. Targets Base.metadata; url comes from Settings (§13)."""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from karverktyg.db.models import Base
from karverktyg.settings import Settings

config = context.config
# A caller (e.g. db-bootstrap) may inject the URL via the Config; otherwise take
# it from Settings.
url = config.get_main_option("sqlalchemy.url") or Settings().database_url
config.set_main_option("sqlalchemy.url", url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
