"""Independent protection review records and immutable lease requirements."""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
from alembic import op

revision = "hypermesh_0064_protection"
down_revision = "hypermesh_0063_model_budget"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hypermesh_leases", sa.Column("protection_policy_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("hypermesh_leases", sa.Column("protection_requirements", pg.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.create_check_constraint("ck_hm_lease_protection", "hypermesh_leases", "protection_policy_version = 1 AND protection_requirements IN ('[]'::jsonb, '[\"physical_memory\"]'::jsonb, '[\"confidential_execution\"]'::jsonb, '[\"physical_memory\",\"confidential_execution\"]'::jsonb, '[\"confidential_execution\",\"physical_memory\"]'::jsonb)")
    op.create_table(
        "hypermesh_protection_approvals",
        sa.Column("id", pg.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", pg.UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("mode", sa.String(32), nullable=False),
        sa.Column("binding", pg.JSONB(), nullable=False),
        sa.Column("evidence_sha256", sa.String(64), nullable=False),
        sa.Column("reviewed_by", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by", pg.UUID(as_uuid=True)),
        sa.Column("revocation_reason", sa.String(256)),
        sa.CheckConstraint("mode IN ('physical_memory', 'confidential_execution')", name="ck_hm_protection_mode"),
        sa.CheckConstraint("expires_at > observed_at AND expires_at <= observed_at + interval '24 hours' AND reviewed_at >= observed_at AND reviewed_at < expires_at", name="ck_hm_protection_window"),
        sa.CheckConstraint("evidence_sha256 ~ '^[0-9a-f]{64}$'", name="ck_hm_protection_digest"),
        sa.CheckConstraint("(revoked_at IS NULL AND revoked_by IS NULL AND revocation_reason IS NULL) OR (revoked_at IS NOT NULL AND revoked_by IS NOT NULL AND length(revocation_reason) > 0 AND revoked_at >= reviewed_at)", name="ck_hm_protection_revocation"),
    )
    op.create_index("ix_hm_protection_device", "hypermesh_protection_approvals", ["tenant_id", "device_id", "expires_at"])
    op.execute("ALTER TABLE hypermesh_protection_approvals ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE hypermesh_protection_approvals FORCE ROW LEVEL SECURITY")
    predicate = "tenant_id::text = nullif(current_setting('app.current_tenant_id', true), '')"
    for operation in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        clause = f"WITH CHECK ({predicate})" if operation == "INSERT" else f"USING ({predicate})"
        if operation == "UPDATE":
            clause += f" WITH CHECK ({predicate})"
        op.execute(f"CREATE POLICY tenant_isolation_{operation.lower()} ON hypermesh_protection_approvals FOR {operation} {clause}")
    op.execute("""
    CREATE FUNCTION hm_protection_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_TABLE_NAME = 'hypermesh_leases' THEN
        IF NEW.protection_policy_version <> OLD.protection_policy_version
           OR NEW.protection_requirements <> OLD.protection_requirements THEN
          RAISE EXCEPTION 'lease protection policy is immutable';
        END IF;
      ELSE
        IF (to_jsonb(NEW) - ARRAY['revoked_at','revoked_by','revocation_reason'])
           <> (to_jsonb(OLD) - ARRAY['revoked_at','revoked_by','revocation_reason'])
           OR (OLD.revoked_at IS NOT NULL AND to_jsonb(NEW) <> to_jsonb(OLD)) THEN
          RAISE EXCEPTION 'protection approval is immutable';
        END IF;
      END IF;
      RETURN NEW;
    END $$
    """)
    for table in ("hypermesh_leases", "hypermesh_protection_approvals"):
        op.execute(f"CREATE TRIGGER protection_immutable BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION hm_protection_immutable()")


def downgrade():
    op.execute("DROP TRIGGER protection_immutable ON hypermesh_leases")
    op.drop_table("hypermesh_protection_approvals")
    op.execute("DROP FUNCTION hm_protection_immutable()")
    op.drop_constraint("ck_hm_lease_protection", "hypermesh_leases")
    op.drop_column("hypermesh_leases", "protection_requirements")
    op.drop_column("hypermesh_leases", "protection_policy_version")
