"""Durable callback ownership; no pool connection held across payment I/O."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "hypermesh_0062_payment_claim"
down_revision = "hypermesh_0062_model_poll_claims"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hypermesh_payment_callback_claims",
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("billing_record_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("token", UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.execute("ALTER TABLE hypermesh_payment_callback_claims ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE hypermesh_payment_callback_claims FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY tenant_isolation ON hypermesh_payment_callback_claims
        USING (tenant_id::text = nullif(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id::text = nullif(current_setting('app.current_tenant_id', true), ''))""")


def downgrade():
    raise RuntimeError("Disable payment callbacks before removing their ownership fence")
