"""Hypermesh sell_pause job+result schema lock (H2).

Revision ID: 0014_sell_pause
Revises: 0013_ticket_purpose
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0014_sell_pause"
down_revision = "0013_ticket_purpose"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_devices "
            "ADD COLUMN IF NOT EXISTS sell_state VARCHAR(16) NOT NULL DEFAULT 'n/a'"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_jobs "
            "ADD COLUMN IF NOT EXISTS until TIMESTAMPTZ"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_jobs "
            "ADD COLUMN IF NOT EXISTS sell_state VARCHAR(16)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE hypermesh_jobs DROP COLUMN IF EXISTS sell_state"))
    op.execute(sa.text("ALTER TABLE hypermesh_jobs DROP COLUMN IF EXISTS until"))
    op.execute(sa.text("ALTER TABLE hypermesh_devices DROP COLUMN IF EXISTS sell_state"))
