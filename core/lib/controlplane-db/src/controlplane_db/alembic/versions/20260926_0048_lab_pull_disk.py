"""Host disk free space and catalog weight size for lab_pull.

Revision ID: 0048_lab_pull_disk
Revises: 0047_event_handler_idempotency

lab_pull is skipped when health.disk_free_bytes is absent, or when
free space plus health.model_cache_evictable_bytes, when that field is
present, is below the catalog size plus a safety margin. Both heartbeat
fields are stored on the device health row with the other health
fields. Unknown free space fails closed. Model size lives on the
catalog row, not in infra config.
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
            "ALTER TABLE hypermesh_device_health "
            "ADD COLUMN IF NOT EXISTS disk_free_bytes BIGINT"
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'ck_hm_health_disk_free'
                ) THEN
                    ALTER TABLE hypermesh_device_health
                    ADD CONSTRAINT ck_hm_health_disk_free
                    CHECK (disk_free_bytes IS NULL OR disk_free_bytes >= 0);
                END IF;
            END $$;
            """
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_device_health "
            "ADD COLUMN IF NOT EXISTS model_cache_evictable_bytes BIGINT"
        )
    )
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'ck_hm_health_cache_evictable'
                ) THEN
                    ALTER TABLE hypermesh_device_health
                    ADD CONSTRAINT ck_hm_health_cache_evictable
                    CHECK (
                        model_cache_evictable_bytes IS NULL
                        OR model_cache_evictable_bytes >= 0
                    );
                END IF;
            END $$;
            """
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
        sa.text(
            "ALTER TABLE hypermesh_device_health "
            "DROP CONSTRAINT IF EXISTS ck_hm_health_cache_evictable"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_device_health "
            "DROP COLUMN IF EXISTS model_cache_evictable_bytes"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_device_health "
            "DROP CONSTRAINT IF EXISTS ck_hm_health_disk_free"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_device_health "
            "DROP COLUMN IF EXISTS disk_free_bytes"
        )
    )
