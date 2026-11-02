"""Person-scoped SIWE wallet bind (address only, no signature).

Revision ID: 0021_user_wallet_bindings
Revises: 0020_catalog_image_digest
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0021_user_wallet_bindings"
down_revision = "0020_catalog_image_digest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS user_wallet_bindings (
                id UUID PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                keycloak_sub VARCHAR(512) NOT NULL,
                email VARCHAR(512),
                wallet_address VARCHAR(42) NOT NULL,
                bound_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_wallet_bindings_sub "
            "ON user_wallet_bindings (keycloak_sub)"
        )
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_wallet_bindings_address "
            "ON user_wallet_bindings (wallet_address)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TABLE IF EXISTS user_wallet_bindings"))
