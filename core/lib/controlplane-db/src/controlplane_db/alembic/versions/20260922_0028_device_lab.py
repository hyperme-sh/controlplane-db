"""Device lab flag for class-envelope soaks vs enrolled compact-cert.

Revision ID: 0028_device_lab
Revises: 0027_organization_idp_links
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0028_device_lab"
down_revision = "0027_organization_idp_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_devices "
            "ADD COLUMN IF NOT EXISTS lab BOOLEAN NOT NULL DEFAULT false"
        )
    )
    op.execute(
        sa.text("ALTER TABLE hypermesh_devices ALTER COLUMN lab SET DEFAULT false")
    )
    op.execute(
        sa.text("UPDATE hypermesh_devices SET lab = false WHERE lab IS NULL")
    )
    op.execute(
        sa.text("ALTER TABLE hypermesh_devices ALTER COLUMN lab SET NOT NULL")
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE hypermesh_devices DROP COLUMN IF EXISTS lab"))
