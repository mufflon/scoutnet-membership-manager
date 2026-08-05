"""write_run.error — run-level failure reason (§8)

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-05

A run that fails before any chunk is journalled (for example, no snapshot volume
configured) previously left no row the frontend could read, so the poll spun on
"Startar körning…" forever. Record the failure reason on the run itself so the
UI can show it. Nullable column, safe to add in place.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("write_run", sa.Column("error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("write_run", "error")
