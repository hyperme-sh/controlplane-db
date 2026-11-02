"""API key last use and fingerprint for revoke.

Revision ID: 0037_api_key_last_used
Revises: 0036_device_wg_pubkey

last_used_at is stamped by the gateway (at most once a minute per key).
key_fingerprint is sha256(prefix.secret), stored at mint so revoke can
unpublish the fingerprint without the raw secret.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0037_api_key_last_used"
down_revision = "0036_device_wg_pubkey"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE api_keys "
            "ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMPTZ"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE api_keys "
            "ADD COLUMN IF NOT EXISTS key_fingerprint VARCHAR(64)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE api_keys DROP COLUMN IF EXISTS key_fingerprint"))
    op.execute(sa.text("ALTER TABLE api_keys DROP COLUMN IF EXISTS last_used_at"))
