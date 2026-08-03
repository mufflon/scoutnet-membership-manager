"""write run / journal / snapshot tables (§8, §9) — no personal-data columns

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "write_run",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("cohort_year", sa.Integer(), nullable=True),
        sa.Column("parent_run_id", sa.String(length=36), nullable=True, index=True),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("snapshot_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "write_journal",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("run_id", sa.String(length=36), nullable=False, index=True),
        sa.Column("chunk_id", sa.Integer(), nullable=False),
        sa.Column("member_no", sa.String(length=32), nullable=False, index=True),
        sa.Column("intended_status", sa.String(length=16), nullable=False),
        sa.Column("intended_troop_id", sa.Integer(), nullable=False),
        sa.Column("source_troop_id", sa.Integer(), nullable=True),
        sa.Column("state", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_table(
        "snapshot",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("run_id", sa.String(length=36), nullable=True, index=True),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("taken_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("snapshot")
    op.drop_table("write_journal")
    op.drop_table("write_run")
