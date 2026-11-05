"""Durable model retention input for closed accounts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "hypermesh_0075_model_closure"
down_revision = "hypermesh_0074_model_inactivity"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("hypermesh_model_owner_closures",
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("owner_sub", sa.String(512), primary_key=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(256), nullable=False),
        sa.CheckConstraint("closed_at <= recorded_at", name="ck_hm_model_closure_time"))
    op.execute("ALTER TABLE hypermesh_model_owner_closures ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE hypermesh_model_owner_closures FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY tenant_isolation ON hypermesh_model_owner_closures
        USING (tenant_id::text = nullif(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id::text = nullif(current_setting('app.current_tenant_id', true), ''))""")


def downgrade():
    raise RuntimeError("Account closure retention records must not be discarded")
