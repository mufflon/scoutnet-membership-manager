"""initial workflow tables (§9) — no personal-data columns

Revision ID: 0001
Revises:
Create Date: 2026-08-03
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "uppflyttning_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cohort_year", sa.Integer(), nullable=False, index=True),
        sa.Column("member_no", sa.String(length=32), nullable=False, index=True),
        sa.Column("source_avdelning", sa.String(length=64), nullable=True),
        sa.Column("source_troop_id", sa.Integer(), nullable=True),
        sa.Column("target_avdelning", sa.String(length=64), nullable=True),
        sa.Column("target_troop_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("override_target", sa.String(length=64), nullable=True),
        sa.Column("override_stay_until", sa.Integer(), nullable=True),
        sa.Column("override_by", sa.String(length=64), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "finding_ack",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("member_no", sa.String(length=32), nullable=False, index=True),
        sa.Column("finding_type", sa.String(length=48), nullable=False),
        sa.Column("value_hash", sa.String(length=32), nullable=False),
        sa.Column("acknowledged_by", sa.String(length=64), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "message_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("member_no", sa.String(length=32), nullable=False, index=True),
        sa.Column("message_type", sa.String(length=48), nullable=False),
        sa.Column("sent_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "email_template",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_key", sa.String(length=48), nullable=False, unique=True, index=True),
        sa.Column("subject", sa.String(length=256), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.String(length=64), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("email_template")
    op.drop_table("message_log")
    op.drop_table("finding_ack")
    op.drop_table("uppflyttning_entry")
