"""Server default for tenants.custom_domain_status.

Revision ID: 0004_tenant_cd_default
Revises: 0003_user_groups_orgs

Note: revision id must fit alembic_version.version_num (varchar(32)).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_tenant_cd_default"
down_revision = "0003_user_groups_orgs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Aligns DB with ORM server_default so INSERTs may omit custom_domain_status.
    op.execute(
        sa.text(
            "ALTER TABLE tenants ALTER COLUMN custom_domain_status SET DEFAULT 'failed'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("ALTER TABLE tenants ALTER COLUMN custom_domain_status DROP DEFAULT")
    )
