"""Durable, owner-bound automatic host registration requests."""

from alembic import op

revision = "0052_host_registrations"
down_revision = "0051_host_org_bindings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 uses current metadata for fresh installs; existing planes need DDL.
    op.execute("""
        CREATE TABLE IF NOT EXISTS hypermesh_host_registrations (
            id UUID PRIMARY KEY,
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            owner_sub VARCHAR(512) NOT NULL,
            host_org_id UUID NOT NULL,
            request JSONB NOT NULL,
            state VARCHAR(16) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            decided_at TIMESTAMPTZ,
            device_id UUID UNIQUE REFERENCES hypermesh_devices(id),
            CONSTRAINT fk_hm_registration_org_tenant
                FOREIGN KEY (host_org_id, tenant_id)
                REFERENCES organizations(id, tenant_id) ON DELETE CASCADE,
            CONSTRAINT ck_hm_registration_state
                CHECK (state IN ('pending', 'approved', 'denied', 'completed'))
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_hm_registration_owner "
               "ON hypermesh_host_registrations (tenant_id, owner_sub)")
    op.execute("ALTER TABLE hypermesh_host_registrations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE hypermesh_host_registrations FORCE ROW LEVEL SECURITY")
    condition = "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
    for operation in ("select", "insert", "update", "delete"):
        clauses = []
        if operation != "insert":
            clauses.append(f"USING ({condition})")
        if operation in ("insert", "update"):
            clauses.append(f"WITH CHECK ({condition})")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{operation} ON hypermesh_host_registrations")
        op.execute(
            f"CREATE POLICY tenant_isolation_{operation} ON hypermesh_host_registrations "
            f"FOR {operation.upper()} {' '.join(clauses)}"
        )


def downgrade() -> None:
    op.drop_table("hypermesh_host_registrations")
