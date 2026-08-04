"""initial schema (§8, §9, §17) — no personal-data columns

Revision ID: 0001
Revises:
Create Date: 2026-08-04

The complete initial schema. Earlier development revisions were squashed into this
one before the repo was shared (deployments are reset, not migrated), so an
external reader sees one coherent starting point. Future changes add new revisions
on top in the usual way.
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
    op.drop_table("cohort_target")
    op.drop_table("email_template")
    op.drop_table("message_log")
    op.drop_table("finding_ack")
    op.drop_table("uppflyttning_entry")
