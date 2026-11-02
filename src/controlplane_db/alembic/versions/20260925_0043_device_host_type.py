"""Device host_type so a supervisor is not offered as a model host.

Revision ID: 0043_device_host_type
Revises: 0042_roles_unique_per_tenant

model is the default. supervisor enrolls and heartbeats and is kept out
of renter offers. This column is not a certification result.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0043_device_host_type"
down_revision = "0042_roles_unique_per_tenant"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # SET DEFAULT, the backfill, and SET NOT NULL cover a column that was
    # added out of band. A clean upgrade only needs the ADD.
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_devices "
            "ADD COLUMN IF NOT EXISTS host_type VARCHAR(16) NOT NULL DEFAULT 'model'"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_devices ALTER COLUMN host_type SET DEFAULT 'model'"
        )
    )
    op.execute(
        sa.text(
            "UPDATE hypermesh_devices SET host_type = 'model' WHERE host_type IS NULL"
        )
    )
    op.execute(
        sa.text("ALTER TABLE hypermesh_devices ALTER COLUMN host_type SET NOT NULL")
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE hypermesh_devices DROP COLUMN IF EXISTS host_type"))
