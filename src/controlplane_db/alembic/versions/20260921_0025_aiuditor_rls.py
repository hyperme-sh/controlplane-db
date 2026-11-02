"""AIuditor grant tables plus Hypermesh lease.contract_id.

Revision ID: 0025_aiuditor_rls
Revises: 0024_lease_audit

Tenant-scoped SoT for connections, approvals, policies, contracts,
violations, and the AIuditor catalog. Not Hypermesh classes/catalog.
Not TURN / oracles / payments. Prompt bodies and HMAC blobs stay off
these tables. 1.x rail is stripe; on-chain is a later rail value.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0025_aiuditor_rls"
down_revision = "0024_lease_audit"
branch_labels = None
depends_on = None

_TABLES = (
    "aiuditor_connections",
    "aiuditor_approvals",
    "aiuditor_policies",
    "aiuditor_contracts",
    "aiuditor_violations",
    "aiuditor_catalog",
)


def _tenant_policy_sql(table: str, op_name: str) -> str:
    cond = """(
                (current_setting('app.current_tenant_id', true) = '' AND tenant_id IS NULL)
                OR (
                    current_setting('app.current_tenant_id', true) <> ''
                    AND tenant_id IS NOT NULL
                    AND tenant_id = current_setting('app.current_tenant_id', true)::uuid
                )
            )"""
    if op_name == "select":
        return f"""
            CREATE POLICY tenant_isolation_select ON "{table}"
            FOR SELECT
            USING {cond}
            """
    if op_name == "insert":
        return f"""
            CREATE POLICY tenant_isolation_insert ON "{table}"
            FOR INSERT
            WITH CHECK {cond}
            """
    if op_name == "update":
        return f"""
            CREATE POLICY tenant_isolation_update ON "{table}"
            FOR UPDATE
            USING {cond}
            WITH CHECK {cond}
            """
    return f"""
        CREATE POLICY tenant_isolation_delete ON "{table}"
        FOR DELETE
        USING {cond}
        """


def _enable_rls(table: str) -> None:
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    for pol in (
        "tenant_isolation_select",
        "tenant_isolation_insert",
        "tenant_isolation_update",
        "tenant_isolation_delete",
    ):
        op.execute(sa.text(f'DROP POLICY IF EXISTS {pol} ON "{table}"'))
    for kind in ("select", "insert", "update", "delete"):
        op.execute(sa.text(_tenant_policy_sql(table, kind)))


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS aiuditor_connections (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                kind VARCHAR(16) NOT NULL,
                purpose VARCHAR(16) NOT NULL,
                device_id UUID,
                endpoint VARCHAR(2048),
                credential_ref VARCHAR(128),
                lease_id UUID,
                status VARCHAR(16) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_aiuditor_connections_tenant "
            "ON aiuditor_connections (tenant_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_aiuditor_connections_tenant_lease "
            "ON aiuditor_connections (tenant_id, lease_id)"
        )
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS aiuditor_approvals (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                lease_id UUID,
                connection_id UUID,
                purpose VARCHAR(32) NOT NULL,
                who VARCHAR(256) NOT NULL,
                why VARCHAR(16) NOT NULL,
                prompt_class VARCHAR(64),
                status VARCHAR(16) NOT NULL,
                decision VARCHAR(32),
                resolved_by VARCHAR(256),
                created_at TIMESTAMPTZ NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                resolved_at TIMESTAMPTZ,
                consumed_at TIMESTAMPTZ
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_aiuditor_approvals_tenant "
            "ON aiuditor_approvals (tenant_id)"
        )
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS aiuditor_policies (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                purpose VARCHAR(32) NOT NULL,
                prompt_class VARCHAR(64),
                connection_id UUID,
                disposition VARCHAR(16) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_aiuditor_policies_tenant "
            "ON aiuditor_policies (tenant_id)"
        )
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS aiuditor_contracts (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                parties JSONB NOT NULL,
                meters JSONB NOT NULL,
                rail VARCHAR(32) NOT NULL,
                until TIMESTAMPTZ NOT NULL,
                dispute_tip VARCHAR(120),
                connection_id UUID,
                lease_id UUID,
                status VARCHAR(16) NOT NULL,
                signed_by VARCHAR(256),
                created_at TIMESTAMPTZ NOT NULL,
                signed_at TIMESTAMPTZ
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_aiuditor_contracts_tenant "
            "ON aiuditor_contracts (tenant_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_aiuditor_contracts_tenant_lease "
            "ON aiuditor_contracts (tenant_id, lease_id)"
        )
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS aiuditor_violations (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                contract_id UUID NOT NULL,
                lease_id UUID,
                kind VARCHAR(32) NOT NULL,
                action VARCHAR(16) NOT NULL,
                reason VARCHAR(120),
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_aiuditor_violations_tenant "
            "ON aiuditor_violations (tenant_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_aiuditor_violations_tenant_contract "
            "ON aiuditor_violations (tenant_id, contract_id)"
        )
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS aiuditor_catalog (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                title VARCHAR(120) NOT NULL,
                backend VARCHAR(32) NOT NULL,
                class_id VARCHAR(64),
                catalog_id VARCHAR(64),
                connection_id UUID,
                meters JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_aiuditor_catalog_tenant "
            "ON aiuditor_catalog (tenant_id)"
        )
    )

    for table in _TABLES:
        _enable_rls(table)

    op.execute(
        sa.text(
            "ALTER TABLE hypermesh_leases "
            "ADD COLUMN IF NOT EXISTS contract_id UUID"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE hypermesh_leases DROP COLUMN IF EXISTS contract_id"))
    for table in reversed(_TABLES):
        for pol in (
            "tenant_isolation_select",
            "tenant_isolation_insert",
            "tenant_isolation_update",
            "tenant_isolation_delete",
        ):
            op.execute(sa.text(f'DROP POLICY IF EXISTS {pol} ON "{table}"'))
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{table}"'))
