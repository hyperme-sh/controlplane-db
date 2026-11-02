"""Hypermesh enroll/join role pin (host | gateway | plane).

Revision ID: 0018_plane_role
Revises: 0017_device_site_id
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_plane_role"
down_revision = "0017_device_site_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_devices "
            "ADD COLUMN IF NOT EXISTS role VARCHAR(16) NOT NULL DEFAULT 'host'"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_gateways "
            "ADD COLUMN IF NOT EXISTS role VARCHAR(16) NOT NULL DEFAULT 'gateway'"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE hypermesh_gateways DROP COLUMN IF EXISTS role"))
    op.execute(sa.text("ALTER TABLE hypermesh_devices DROP COLUMN IF EXISTS role"))
