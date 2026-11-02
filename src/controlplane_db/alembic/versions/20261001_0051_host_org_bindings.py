"""Bind host organizations to verified identities, never the oldest tenant org."""

from alembic import op

revision = "0051_host_org_bindings"
down_revision = "0050_host_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 creates current ORM metadata on fresh installs, so the schema may
    # already exist there. Upgrading an existing deployment creates it here.
    op.execute("""
        DO $migration$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'organizations'::regclass
                  AND conname = 'uq_organizations_id_tenant'
            ) THEN
                ALTER TABLE organizations ADD CONSTRAINT uq_organizations_id_tenant
                    UNIQUE (id, tenant_id);
            END IF;
        END $migration$;
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS host_organization_bindings (
            tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            keycloak_sub VARCHAR(512) NOT NULL,
            organization_id UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (tenant_id, keycloak_sub),
            CONSTRAINT fk_host_org_binding_organization_tenant
                FOREIGN KEY (organization_id, tenant_id)
                REFERENCES organizations(id, tenant_id) ON DELETE CASCADE,
            CONSTRAINT uq_host_org_binding_organization UNIQUE (organization_id)
        )
    """)
    op.execute("ALTER TABLE host_organization_bindings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE host_organization_bindings FORCE ROW LEVEL SECURITY")
    condition = "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
    for operation in ("select", "insert", "update", "delete"):
        clauses = []
        if operation != "insert":
            clauses.append(f"USING ({condition})")
        if operation in ("insert", "update"):
            clauses.append(f"WITH CHECK ({condition})")
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{operation} ON host_organization_bindings")
        op.execute(
            f"CREATE POLICY tenant_isolation_{operation} ON host_organization_bindings "
            f"FOR {operation.upper()} {' '.join(clauses)}"
        )
    # Deliberately no inferred backfill. Historical devices/orgs do not contain
    # enough evidence to assign an owner from a name, email or creation order.


def downgrade() -> None:
    op.drop_table("host_organization_bindings")
    op.drop_constraint("uq_organizations_id_tenant", "organizations", type_="unique")
