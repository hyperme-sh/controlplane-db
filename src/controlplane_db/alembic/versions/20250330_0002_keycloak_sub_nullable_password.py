"""keycloak_sub on users; nullable password for Keycloak-only accounts.

Revision ID: 0002
Revises: 0001
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_keycloak_sub"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 uses metadata.create_all(); current models already include keycloak_sub and
    # nullable password. This revision must stay for DBs that ran an older 0001, and be
    # a no-op when the schema already matches.
    op.execute(
        sa.text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS keycloak_sub VARCHAR(512)"
        )
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_keycloak_sub_unique "
            "ON users (keycloak_sub) WHERE keycloak_sub IS NOT NULL"
        )
    )
    op.execute(sa.text("ALTER TABLE users ALTER COLUMN password DROP NOT NULL"))


def downgrade() -> None:
    op.alter_column(
        "users",
        "password",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.drop_index("ix_users_keycloak_sub_unique", table_name="users")
    op.drop_column("users", "keycloak_sub")
