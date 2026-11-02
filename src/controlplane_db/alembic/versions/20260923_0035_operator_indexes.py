"""Tenant indexes declared on the operator ORM models.

Revision ID: 0035_operator_indexes
Revises: 0034_operator_console

0034 created operator_bans, operator_audit, and operator_peers without the
tenant_id indexes the models declare. Create them when missing.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0035_operator_indexes"
down_revision = "0034_operator_console"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_operator_bans_tenant "
            "ON operator_bans (tenant_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_operator_audit_tenant "
            "ON operator_audit (tenant_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_operator_peers_tenant "
            "ON operator_peers (tenant_id)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_operator_peers_tenant"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_operator_audit_tenant"))
    op.execute(sa.text("DROP INDEX IF EXISTS ix_operator_bans_tenant"))
