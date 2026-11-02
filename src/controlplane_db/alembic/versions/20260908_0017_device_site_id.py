"""Hypermesh device.site_id bind (Brewnix enqueue scope).

Revision ID: 0017_device_site_id
Revises: 0016_auditor_tickets
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0017_device_site_id"
down_revision = "0016_auditor_tickets"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_devices "
            "ADD COLUMN IF NOT EXISTS site_id VARCHAR(128)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_hm_devices_tenant_site "
            "ON hypermesh_devices (tenant_id, site_id)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_hm_devices_tenant_site"))
    op.execute(sa.text("ALTER TABLE hypermesh_devices DROP COLUMN IF EXISTS site_id"))
