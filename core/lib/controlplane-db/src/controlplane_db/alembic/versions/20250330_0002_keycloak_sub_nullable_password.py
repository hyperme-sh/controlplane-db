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
    op.add_column("users", sa.Column("keycloak_sub", sa.String(512), nullable=True))
    op.create_index(
        "ix_users_keycloak_sub_unique",
        "users",
        ["keycloak_sub"],
        unique=True,
        postgresql_where=sa.text("keycloak_sub IS NOT NULL"),
    )
    op.alter_column(
        "users",
        "password",
        existing_type=sa.Text(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "users",
        "password",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.drop_index("ix_users_keycloak_sub_unique", table_name="users")
    op.drop_column("users", "keycloak_sub")
