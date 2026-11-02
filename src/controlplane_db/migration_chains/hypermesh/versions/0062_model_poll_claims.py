"""Shared expiring device poll ownership; no SQL connection held across remote I/O."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "hypermesh_0062_model_poll_claims"
down_revision = "hypermesh_0061_model_lease"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hypermesh_model_poll_claims",
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("device_id", UUID(as_uuid=True), sa.ForeignKey("hypermesh_devices.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("token", UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute("ALTER TABLE hypermesh_model_poll_claims ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE hypermesh_model_poll_claims FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY tenant_isolation ON hypermesh_model_poll_claims
        USING (tenant_id::text = nullif(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id::text = nullif(current_setting('app.current_tenant_id', true), ''))""")


def downgrade():
    raise RuntimeError("Disable model polling before removing its ownership fence")
