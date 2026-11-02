"""organizations, groups, user_group_memberships + user soft-delete and sociacl; RLS.

Revision ID: 0003
Revises: 0002_keycloak_sub
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_user_groups_orgs"
down_revision = "0002_keycloak_sub"
branch_labels = None
depends_on = None

_RLS_TABLES = ("organizations", "groups", "user_group_memberships")


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
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS sociacl_attributes JSONB"
        )
    )

    op.execute(
        sa.text("""
            CREATE TABLE IF NOT EXISTS organizations (
                id UUID NOT NULL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                legal_name VARCHAR(512) NOT NULL
            )
        """)
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_organizations_tenant_legal_name "
            "ON organizations (tenant_id, legal_name)"
        )
    )

    op.execute(
        sa.text("""
            CREATE TABLE IF NOT EXISTS groups (
                id UUID NOT NULL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                role_id UUID NOT NULL REFERENCES roles(id) ON DELETE RESTRICT
            )
        """)
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_groups_tenant_name "
            "ON groups (tenant_id, name)"
        )
    )

    op.execute(
        sa.text("""
            CREATE TABLE IF NOT EXISTS user_group_memberships (
                id UUID NOT NULL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                group_id UUID NOT NULL REFERENCES groups(id) ON DELETE CASCADE
            )
        """)
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_user_group_memberships_user_group "
            "ON user_group_memberships (user_id, group_id)"
        )
    )

    for t in _RLS_TABLES:
        _enable_rls(t)


def downgrade() -> None:
    for table in _RLS_TABLES:
        for pol in (
            "tenant_isolation_select",
            "tenant_isolation_insert",
            "tenant_isolation_update",
            "tenant_isolation_delete",
        ):
            op.execute(sa.text(f'DROP POLICY IF EXISTS {pol} ON "{table}"'))
        op.execute(sa.text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))

    op.execute(sa.text("DROP TABLE IF EXISTS user_group_memberships CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS groups CASCADE"))
    op.execute(sa.text("DROP TABLE IF EXISTS organizations CASCADE"))

    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS sociacl_attributes"))
    op.execute(sa.text("ALTER TABLE users DROP COLUMN IF EXISTS deleted_at"))
