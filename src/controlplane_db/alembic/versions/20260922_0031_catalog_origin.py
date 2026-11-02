"""Catalog origin + admission_id for upload promote.

Revision ID: 0031_catalog_origin
Revises: 0030_aiuditor_crawl

Upload admission allow stamps origin=upload and admission_id. Lab soak stubs
use origin=lab. Seed rows default to origin=seed. Door gates upload only.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0031_catalog_origin"
down_revision = "0030_aiuditor_crawl"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_catalog "
            "ADD COLUMN IF NOT EXISTS origin VARCHAR(16) NOT NULL DEFAULT 'seed'"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_catalog "
            "ADD COLUMN IF NOT EXISTS admission_id UUID"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE hypermesh_catalog DROP COLUMN IF EXISTS admission_id"))
    op.execute(sa.text("ALTER TABLE hypermesh_catalog DROP COLUMN IF EXISTS origin"))
