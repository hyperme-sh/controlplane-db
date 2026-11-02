"""Allow host peers without a lease; clear terminal lease associations (#206).

Revision ID: 0049_idle_tunnel_lease
Revises: 0048_lab_pull_disk

Apply before deploying the nullable tunnel API. Host peer keys and addresses
are preserved. Historical ownership stays in the lease/job/audit records.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0049_idle_tunnel_lease"
down_revision = "0048_lab_pull_disk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("hypermesh_tunnels", "lease_id", existing_type=sa.UUID(), nullable=True)
    op.execute(sa.text("""
        UPDATE hypermesh_tunnels AS tunnel
        SET lease_id = NULL, expires_at = NULL
        FROM hypermesh_leases AS lease
        WHERE tunnel.tenant_id = lease.tenant_id
          AND tunnel.lease_id = lease.id
          AND tunnel.status = 'allocated'
          AND lease.status IN ('ended', 'failed', 'refunded')
    """))


def downgrade() -> None:
    # Refuse an unsafe downgrade while idle peers exist. Never invent a lease
    # ID or delete a host's working WireGuard peer to satisfy the old schema.
    op.alter_column("hypermesh_tunnels", "lease_id", existing_type=sa.UUID(), nullable=False)
