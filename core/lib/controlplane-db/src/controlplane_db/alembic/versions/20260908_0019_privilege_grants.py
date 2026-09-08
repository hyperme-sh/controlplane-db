"""Hypermesh fyber.privilege_grant/v0 plane store.

Revision ID: 0019_privilege_grants
Revises: 0018_plane_role
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0019_privilege_grants"
down_revision = "0018_plane_role"
branch_labels = None
depends_on = None

_TABLE = "hypermesh_privilege_grants"


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
            f"""
            CREATE TABLE IF NOT EXISTS {_TABLE} (
                grant_id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                site_id VARCHAR(128) NOT NULL,
                grant_schema VARCHAR(64) NOT NULL,
                incident_id UUID NOT NULL,
                trace_id UUID NOT NULL,
                requested_at TIMESTAMPTZ NOT NULL,
                requested_by JSONB NOT NULL,
                reason_redacted VARCHAR(1000) NOT NULL,
                asks JSONB NOT NULL,
                rails_profile_requested VARCHAR(32),
                ttl_s_requested INTEGER NOT NULL,
                blast_radius VARCHAR(16) NOT NULL,
                status VARCHAR(16) NOT NULL,
                resolution JSONB,
                active_until TIMESTAMPTZ,
                parent_grant_id UUID,
                ticket_id UUID,
                integrity JSONB
            )
            """
        )
    )
    op.execute(
        sa.text(f"CREATE INDEX IF NOT EXISTS ix_hm_privilege_grants_tenant ON {_TABLE} (tenant_id)")
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_hm_privilege_grants_tenant_site "
            f"ON {_TABLE} (tenant_id, site_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_hm_privilege_grants_tenant_site_status "
            f"ON {_TABLE} (tenant_id, site_id, status)"
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
