"""Partial index on live leases for the heartbeat-loss sweep.

The sweep reads only a tenant's ``starting`` and ``active`` leases every
interval. Without a status-aware index PostgreSQL walks every lease row for
the tenant, including any number of old or unpaid offers. The partial index
holds only live rows, so the sweep's cost tracks the number of live leases.
"""

import sqlalchemy as sa
from alembic import op

revision = "hypermesh_0058_live_lease_index"
down_revision = "hypermesh_0057_lease_usdc"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        "ix_hm_leases_tenant_live",
        "hypermesh_leases",
        ["tenant_id", "status"],
        postgresql_where=sa.text("status IN ('starting', 'active')"),
    )


def downgrade():
    op.drop_index("ix_hm_leases_tenant_live", table_name="hypermesh_leases")
