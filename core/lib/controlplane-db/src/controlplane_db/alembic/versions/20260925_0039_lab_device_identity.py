"""Point lab soaks at the live AGX and retire the placeholder.

Revision ID: 0039_lab_device_identity
Revises: 0038_aiuditor_size_bytes_bigint

The live box FYBER-AGX64-1 (f6124d28-772c-4f1f-8e03-1a7a17724381) on the
marketplace tenant becomes lab=true when that row exists. Listing
(sell_state), certification (path_b_state), and price columns are not
touched. A missing row is a no-op (fresh DB, CI).

The never-heartbeated seed device FYBER-AGX-ORIN-64-001
(a6400000-0640-4000-8000-000000000001) is kept, with lab cleared and
enrolled cleared and sell_state paused. It is not deleted.

Re-running the UPDATEs is safe. Downgrade is a no-op: the previous lab
bit is not stored, and putting the placeholder back on the lab path
would undo the correction.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0039_lab_device_identity"
down_revision = "0038_aiuditor_size_bytes_bigint"
branch_labels = None
depends_on = None

_MARKETPLACE_TENANT = "8f8e8d8c-7b6a-4a59-8c3d-2e1f0a9b8c7d"
_LIVE_DEVICE = "f6124d28-772c-4f1f-8e03-1a7a17724381"
_PLACEHOLDER_DEVICE = "a6400000-0640-4000-8000-000000000001"


def upgrade() -> None:
    # FORCE ROW LEVEL SECURITY applies to the table owner. The GUC makes
    # the updates visible to a non-superuser migration role. Absent rows
    # update zero records.
    op.execute(
        sa.text(
            "SELECT set_config('app.current_tenant_id', :tid, true)"
        ).bindparams(tid=_MARKETPLACE_TENANT)
    )
    op.execute(
        sa.text(
            """
            UPDATE hypermesh_devices
            SET lab = true
            WHERE id = :device_id
              AND tenant_id = :tenant_id
            """
        ).bindparams(device_id=_LIVE_DEVICE, tenant_id=_MARKETPLACE_TENANT)
    )
    op.execute(
        sa.text(
            """
            UPDATE hypermesh_devices
            SET lab = false,
                enrolled = false,
                sell_state = 'paused'
            WHERE id = :device_id
              AND tenant_id = :tenant_id
            """
        ).bindparams(device_id=_PLACEHOLDER_DEVICE, tenant_id=_MARKETPLACE_TENANT)
    )


def downgrade() -> None:
    # No-op. Restoring lab=true on the placeholder would put the
    # never-heartbeated seed box back on the soak path. Clearing lab on
    # the live box would drop a flag we cannot prove was false before.
    pass
