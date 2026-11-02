"""Hypermesh catalog.image_digest (OCI pin, distinct from file_hash).

Revision ID: 0020_catalog_image_digest
Revises: 0019_privilege_grants
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0020_catalog_image_digest"
down_revision = "0019_privilege_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_catalog "
            "ADD COLUMN IF NOT EXISTS image_digest VARCHAR(256)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE hypermesh_catalog DROP COLUMN IF EXISTS image_digest"))
