"""Job source_ref for lab_pull trusted fetch.

Revision ID: 0032_job_source_ref
Revises: 0031_catalog_origin

lab_pull carries a content pin (image_digest=sha256:…) and a trusted
source_ref (repo@rev/file). The host agent fetches; the crawler never does.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0032_job_source_ref"
down_revision = "0031_catalog_origin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_jobs "
            "ADD COLUMN IF NOT EXISTS source_ref VARCHAR(512)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE hypermesh_jobs DROP COLUMN IF EXISTS source_ref"))
