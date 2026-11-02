"""Host WireGuard public key on hypermesh_devices.

Revision ID: 0036_device_wg_pubkey
Revises: 0035_operator_indexes

Device persist has included wg_public_key since the private key left the
plane. The ORM column was missing, so every device upsert raised TypeError
and hypermesh-service exited before it listened.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0036_device_wg_pubkey"
down_revision = "0035_operator_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_devices "
            "ADD COLUMN IF NOT EXISTS wg_public_key VARCHAR(128)"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("ALTER TABLE hypermesh_devices DROP COLUMN IF EXISTS wg_public_key")
    )
