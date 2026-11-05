"""Durable account closure intake owned by user-service."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "platform_0058_closure_requests"
down_revision = "platform_0057_checkpoint_replay"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("account_closure_requests",
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("subject", sa.String(512), primary_key=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_by", sa.String(512), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.CheckConstraint("source IN ('self_service', 'operator')", name="ck_account_closure_source"),
        sa.CheckConstraint("length(btrim(subject)) > 0", name="ck_account_closure_subject"),
        sa.CheckConstraint("length(btrim(requested_by)) > 0", name="ck_account_closure_actor"))
    op.create_index("ix_account_closure_requested", "account_closure_requests", ["tenant_id", "requested_at", "subject"])
    op.execute("ALTER TABLE account_closure_requests ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE account_closure_requests FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY tenant_isolation ON account_closure_requests
        USING (tenant_id::text = nullif(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id::text = nullif(current_setting('app.current_tenant_id', true), ''))""")


def downgrade():
    # FORCE RLS applies even to the table owner. Without unrestricted visibility,
    # PostgreSQL must refuse the guard query rather than hide other tenants.
    op.execute("SET LOCAL row_security = off")
    op.execute("LOCK TABLE account_closure_requests IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM account_closure_requests) THEN
            RAISE EXCEPTION 'cannot discard account closure requests';
        END IF;
    END $$""")
    op.drop_table("account_closure_requests")
