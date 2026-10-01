"""Frozen inactive onboarding certification runs and reviewed model sources."""
from alembic import op

revision = "0053_onboarding_runs"
down_revision = "0052_host_registrations"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.execute("ALTER TABLE hypermesh_catalog ADD COLUMN IF NOT EXISTS onboarding_source_ref VARCHAR(1024)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS hypermesh_onboarding_runs (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            device_id UUID NOT NULL REFERENCES hypermesh_devices(id),
            registration_id UUID NOT NULL REFERENCES hypermesh_host_registrations(id),
            manifest JSONB NOT NULL,
            manifest_sha256 VARCHAR(64) NOT NULL,
            state VARCHAR(16) NOT NULL,
            evidence JSONB,
            created_at TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            completed_at TIMESTAMPTZ,
            approved_by VARCHAR(512),
            approved_at TIMESTAMPTZ,
            CONSTRAINT ck_hm_onboarding_state CHECK (state IN ('planned', 'passed', 'failed'))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_hm_onboarding_device ON hypermesh_onboarding_runs (tenant_id, device_id)")
    op.execute("ALTER TABLE hypermesh_onboarding_runs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE hypermesh_onboarding_runs FORCE ROW LEVEL SECURITY")
    condition = "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
    for operation in ("select", "insert", "update", "delete"):
        clauses = []
        if operation != "insert":
            clauses.append(f"USING ({condition})")
        if operation in ("insert", "update"):
            clauses.append(f"WITH CHECK ({condition})")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{operation} ON hypermesh_onboarding_runs")
        op.execute(f"CREATE POLICY tenant_isolation_{operation} ON hypermesh_onboarding_runs FOR {operation.upper()} {' '.join(clauses)}")

def downgrade() -> None:
    op.drop_table("hypermesh_onboarding_runs")
    op.drop_column("hypermesh_catalog", "onboarding_source_ref")
