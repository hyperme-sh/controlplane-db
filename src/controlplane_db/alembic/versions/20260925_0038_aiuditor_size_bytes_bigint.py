"""Widen aiuditor size_bytes from INTEGER to BIGINT.

Revision ID: 0038_aiuditor_size_bytes_bigint
Revises: 0037_api_key_last_used

GGUF metadata can exceed 2^31-1 bytes (about 2.1 GiB). 0030 left
aiuditor_candidates.size_bytes and aiuditor_admissions.size_bytes as
INTEGER, and the ORM Integer bind is what Postgres rejects. This
revision does not edit 0030.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0038_aiuditor_size_bytes_bigint"
down_revision = "0037_api_key_last_used"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE aiuditor_candidates "
            "ALTER COLUMN size_bytes TYPE BIGINT"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE aiuditor_admissions "
            "ALTER COLUMN size_bytes TYPE BIGINT"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE aiuditor_candidates "
            "ALTER COLUMN size_bytes TYPE INTEGER"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE aiuditor_admissions "
            "ALTER COLUMN size_bytes TYPE INTEGER"
        )
    )
