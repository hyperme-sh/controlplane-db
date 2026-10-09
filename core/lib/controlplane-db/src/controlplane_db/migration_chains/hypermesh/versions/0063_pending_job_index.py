"""Bound per-device pending job polling to the active queue."""

import sqlalchemy as sa
from alembic import op

revision = "hypermesh_0063_pending_jobs"
down_revision = "hypermesh_0062_payment_claim"
branch_labels = None
depends_on = None

def upgrade():
    op.create_index("ix_hm_jobs_pending_device", "hypermesh_jobs", ["tenant_id", "device_id", "created_at", "id"], postgresql_where=sa.text("status = 'pending'"))

def downgrade():
    op.drop_index("ix_hm_jobs_pending_device", table_name="hypermesh_jobs")
