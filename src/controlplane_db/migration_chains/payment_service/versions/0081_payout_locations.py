"""Tenant-isolated, revision-bound postal evidence without raw street addresses."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "payment_service_0081_location"
down_revision = "payment_service_0080_fin_state"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "connect_payout_locations",
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), primary_key=True),
        sa.Column("host_org_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("revision", UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("address_digest", sa.String(64)),
        sa.Column("state", sa.String(2)),
        sa.Column("county_fips", sa.String(5)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.Column("account_id", sa.String(255)),
        sa.Column("enrollment_attempt_id", UUID(as_uuid=True)),
        sa.CheckConstraint("status IN ('pending', 'verified')", name="ck_payout_location_status"),
        sa.CheckConstraint("status <> 'verified' OR (address_digest IS NOT NULL AND expires_at IS NOT NULL AND county_fips IS NOT NULL)", name="ck_payout_location_evidence"),
    )
    op.execute("ALTER TABLE connect_payout_locations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE connect_payout_locations FORCE ROW LEVEL SECURITY")
    condition = "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
    op.execute(f"CREATE POLICY payout_location_tenant ON connect_payout_locations USING ({condition}) WITH CHECK ({condition})")


def downgrade():
    op.execute("SET LOCAL row_security=off")
    op.execute("LOCK TABLE connect_payout_locations IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM connect_payout_locations) THEN
      RAISE EXCEPTION 'Cannot discard payout address enforcement state' USING ERRCODE='23514';
      END IF; END $$""")
    op.drop_table("connect_payout_locations")
