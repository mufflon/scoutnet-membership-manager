"""write_journal patrull columns — intended/source patrol_id (§4, §8)

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-06

A move can now place a member in a patrull within the target avdelning
(``update/membership`` accepts ``patrol_id``, §4). Record the patrull the run
sets and the observed prior patrull, so an undo restores the patrull the same
way it restores the avdelning — computed from what *was*, never from the
intended change (§8). Both nullable and safe to add in place: a move omits
patrol_id when the target avdelning has no known patrull, and an existing
journal row simply has NULL for both.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("write_journal", sa.Column("intended_patrol_id", sa.Integer(), nullable=True))
    op.add_column("write_journal", sa.Column("source_patrol_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("write_journal", "source_patrol_id")
    op.drop_column("write_journal", "intended_patrol_id")
