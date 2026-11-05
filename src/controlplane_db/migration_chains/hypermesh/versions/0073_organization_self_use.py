"""Owner-approved organization self-use without marketplace money."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "hypermesh_0073_self_use"
down_revision = "hypermesh_0072_receipt_cert"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hypermesh_leases", sa.Column("self_use", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_table("hypermesh_self_use_members",
        sa.Column("tenant_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("host_org_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("member_subject", UUID(as_uuid=True), primary_key=True),
        sa.Column("granted_by", UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["host_org_id", "tenant_id"], ["organizations.id", "organizations.tenant_id"],
            name="fk_hm_self_use_organization_tenant", ondelete="CASCADE"))
    op.execute("ALTER TABLE hypermesh_self_use_members ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE hypermesh_self_use_members FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY tenant_isolation ON hypermesh_self_use_members
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
        WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)""")
    op.execute("""CREATE FUNCTION hm_self_use_immutable() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
        IF TG_OP = 'UPDATE' AND NEW.self_use IS DISTINCT FROM OLD.self_use THEN
            RAISE EXCEPTION 'Lease self-use mode cannot change';
        END IF;
        IF NEW.self_use AND (NEW.reserved_hours <> 1 OR NEW.purpose <> 'renter'
            OR NEW.billing_record_id IS NOT NULL OR COALESCE(NEW.gross_cents, 0) <> 0
            OR COALESCE(NEW.payment_amount_atoms, 0) <> 0 OR NEW.payment_test_credit_available) THEN
            RAISE EXCEPTION 'Self-use cannot charge or extend';
        END IF;
        RETURN NEW;
    END $$""")
    op.execute("""CREATE TRIGGER self_use_immutable BEFORE INSERT OR UPDATE ON hypermesh_leases
        FOR EACH ROW EXECUTE FUNCTION hm_self_use_immutable()""")


def downgrade():
    raise RuntimeError("Self-use classification and membership history must not be discarded")
