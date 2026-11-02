"""crypto_agent_budgets (RLS) for Hyperme-style Solana budget envelopes.

Revision ID: 0007_crypto_bdg
Revises: 0006_sociacl_shr
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0007_crypto_bdg"
down_revision = "0006_sociacl_shr"
branch_labels = None
depends_on = None

_TABLE = "crypto_agent_budgets"


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
                id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                label VARCHAR(255),
                owner_pubkey TEXT NOT NULL,
                mint_pubkey TEXT NOT NULL,
                ceiling_lamports BIGINT NOT NULL,
                allocated_lamports BIGINT NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                CONSTRAINT ck_crypto_budget_lamports_nonneg CHECK (
                    ceiling_lamports >= 0 AND allocated_lamports >= 0
                ),
                CONSTRAINT ck_crypto_budget_allocated_le_ceiling CHECK (
                    allocated_lamports <= ceiling_lamports
                )
            )
            """
        )
    )
    op.execute(
        sa.text(f"CREATE INDEX IF NOT EXISTS ix_{_TABLE}_tenant ON {_TABLE} (tenant_id)")
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
    op.execute(sa.text(f'ALTER TABLE "{_TABLE}" NO FORCE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{_TABLE}" DISABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f"DROP TABLE IF EXISTS {_TABLE}"))
