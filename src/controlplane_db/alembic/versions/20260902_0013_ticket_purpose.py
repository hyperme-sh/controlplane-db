"""Purpose on lease tickets and API keys (gateway roadmap slice 3).

Revision ID: 0013_ticket_purpose
Revises: 0012_hypermesh
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0013_ticket_purpose"
down_revision = "0012_hypermesh"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_leases "
            "ADD COLUMN IF NOT EXISTS purpose VARCHAR(32) NOT NULL DEFAULT 'renter'"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_tickets "
            "ADD COLUMN IF NOT EXISTS purpose VARCHAR(32) NOT NULL DEFAULT 'renter'"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE api_keys "
            "ADD COLUMN IF NOT EXISTS purpose VARCHAR(32) NOT NULL DEFAULT 'renter'"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE api_keys DROP COLUMN IF EXISTS purpose"))
    op.execute(sa.text("ALTER TABLE hypermesh_tickets DROP COLUMN IF EXISTS purpose"))
    op.execute(sa.text("ALTER TABLE hypermesh_leases DROP COLUMN IF EXISTS purpose"))
