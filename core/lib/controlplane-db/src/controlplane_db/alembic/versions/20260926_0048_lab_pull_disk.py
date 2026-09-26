"""Host disk free space and catalog weight size for lab_pull.

Revision ID: 0048_lab_pull_disk
Revises: 0047_event_handler_idempotency

lab_pull is skipped when the heartbeat has not reported free bytes, or
when free bytes are below the catalog size plus a safety margin. Both
measures are nullable. Unknown free space fails closed. Model size lives
on the catalog row, not in infra config.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0048_lab_pull_disk"
down_revision = "0047_event_handler_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_devices "
            "ADD COLUMN IF NOT EXISTS disk_free_bytes BIGINT"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_catalog "
            "ADD COLUMN IF NOT EXISTS size_bytes BIGINT"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_jobs "
            "ADD COLUMN IF NOT EXISTS dispatch_skip_reason VARCHAR(256)"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("ALTER TABLE hypermesh_jobs DROP COLUMN IF EXISTS dispatch_skip_reason")
    )
    op.execute(sa.text("ALTER TABLE hypermesh_catalog DROP COLUMN IF EXISTS size_bytes"))
    op.execute(
        sa.text("ALTER TABLE hypermesh_devices DROP COLUMN IF EXISTS disk_free_bytes")
    )
