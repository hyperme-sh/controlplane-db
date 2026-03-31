"""sociacl_share_links + sociacl_recovery_sessions (RLS).

Revision ID: 0006_sociacl_shr
Revises: 0005_acl_casbin
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_sociacl_shr"
down_revision = "0005_acl_casbin"
branch_labels = None
depends_on = None

_T1 = "sociacl_share_links"
_T2 = "sociacl_recovery_sessions"


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
            CREATE TABLE IF NOT EXISTS {_T1} (
                id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                token_hash VARCHAR(64) NOT NULL,
                token_prefix VARCHAR(16) NOT NULL,
                owner_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                group_id UUID REFERENCES groups(id) ON DELETE SET NULL,
                resource_kind VARCHAR(32) NOT NULL,
                resource_descriptor JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                predicate_json JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                mode VARCHAR(32) NOT NULL,
                expires_at TIMESTAMPTZ,
                uses_remaining INTEGER,
                revoked_at TIMESTAMPTZ,
                created_by VARCHAR(512),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{_T1}_token_hash ON {_T1} (token_hash)"
        )
    )
    op.execute(
        sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_{_T1}_tenant ON {_T1} (tenant_id)"
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS {_T2} (
                id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                state VARCHAR(32) NOT NULL,
                idempotency_key VARCHAR(128) NOT NULL,
                expires_at TIMESTAMPTZ NOT NULL,
                metadata JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (tenant_id, idempotency_key)
            )
            """
        )
    )
    op.execute(
        sa.text(f"CREATE INDEX IF NOT EXISTS ix_{_T2}_tenant ON {_T2} (tenant_id)")
    )
    _enable_rls(_T1)
    _enable_rls(_T2)
    # Lookup by token hash without prior tenant GUC (FORCE RLS applies to normal sessions).
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION sociacl_share_lookup_by_hash(p_hash varchar(64))
            RETURNS SETOF {_T1}
            LANGUAGE sql
            SECURITY DEFINER
            SET search_path = public
            STABLE
            AS $$
              SELECT * FROM {_T1} WHERE token_hash = p_hash LIMIT 1;
            $$
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP FUNCTION IF EXISTS sociacl_share_lookup_by_hash(varchar)"))
    for t in (_T2, _T1):
        for pol in (
            "tenant_isolation_select",
            "tenant_isolation_insert",
            "tenant_isolation_update",
            "tenant_isolation_delete",
        ):
            op.execute(sa.text(f'DROP POLICY IF EXISTS {pol} ON "{t}"'))
        op.execute(sa.text(f'ALTER TABLE "{t}" NO FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{t}" DISABLE ROW LEVEL SECURITY'))
        op.execute(sa.text(f"DROP TABLE IF EXISTS {t}"))
