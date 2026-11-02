"""Record the moment a host or instance check fails during a lease.

Revision ID: 0045_lease_failed_at
Revises: 0044_pricing_schema

``failed_at`` is the detection time, not the time the settle request
arrives. A later retry of the refund reads this column. Nullable so
leases that have not failed stay unchanged.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0045_lease_failed_at"
down_revision = "0044_pricing_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 create_all already adds columns that exist on the current models.
    # IF NOT EXISTS covers that path and a database that predates the column.
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_leases "
            "ADD COLUMN IF NOT EXISTS failed_at TIMESTAMPTZ"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE hypermesh_leases DROP COLUMN IF EXISTS failed_at"))
