"""cohort-level target election for new_cohort_avdelning moves (§17)

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cohort_target",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cohort_year", sa.Integer(), nullable=False, index=True),
        sa.Column("bracket", sa.String(length=32), nullable=False),
        sa.Column("target_avdelning", sa.String(length=64), nullable=False),
        sa.Column("target_troop_id", sa.Integer(), nullable=True),
        sa.Column("elected_by", sa.String(length=64), nullable=True),
        sa.Column("elected_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("cohort_year", "bracket", name="uq_cohort_target"),
    )


def downgrade() -> None:
    op.drop_table("cohort_target")
