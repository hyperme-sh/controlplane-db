"""api_keys (tenant-scoped integrations; no RLS — app enforces tenant on CRUD).

Revision ID: 0011_api_keys
Revises: 0010_seller_ai_entitlements
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011_api_keys"
down_revision = "0010_seller_ai_entitlements"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                key_prefix VARCHAR(32) NOT NULL,
                secret_hash VARCHAR(128) NOT NULL,
                name VARCHAR(256),
                scopes JSONB,
                created_by_sub VARCHAR(512),
                revoked_at TIMESTAMPTZ,
                CONSTRAINT uq_api_keys_prefix UNIQUE (key_prefix)
            );
            CREATE INDEX IF NOT EXISTS ix_api_keys_tenant ON api_keys (tenant_id);
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS api_keys"))
