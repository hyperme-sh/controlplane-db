"""Host certification / AGX bench validation override.

Revision ID: 0022_host_cert_override
Revises: 0021_user_wallet_bindings
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0022_host_cert_override"
down_revision = "0021_user_wallet_bindings"
branch_labels = None
depends_on = None

_TABLE = "hypermesh_host_cert_overrides"


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
            "ALTER TABLE hypermesh_devices "
            "ADD COLUMN IF NOT EXISTS schedule_hold BOOLEAN NOT NULL DEFAULT false"
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS {_TABLE} (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                device_id UUID NOT NULL,
                status VARCHAR(16) NOT NULL,
                preempt BOOLEAN NOT NULL DEFAULT true,
                preempted_lease_id UUID,
                lease_stop_job_id UUID,
                cert_job_id UUID,
                held_at TIMESTAMPTZ NOT NULL,
                restored_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ,
                fail_closed BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )
    )
    op.execute(
        sa.text(f"CREATE INDEX IF NOT EXISTS ix_hm_host_cert_overrides_tenant ON {_TABLE} (tenant_id)")
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_hm_host_cert_overrides_tenant_device "
            f"ON {_TABLE} (tenant_id, device_id)"
        )
    )
    _enable_rls(_TABLE)


def downgrade() -> None:
    for pol in (
        "tenant_isolation_select",
        "tenant_isolation_insert",
        "tenant_isolation_update",
        "tenant_isolation_delete",
    ):
        op.execute(sa.text(f'DROP POLICY IF EXISTS {pol} ON "{_TABLE}"'))
    op.execute(sa.text(f'DROP TABLE IF EXISTS "{_TABLE}"'))
    op.execute(sa.text("ALTER TABLE hypermesh_devices DROP COLUMN IF EXISTS schedule_hold"))
