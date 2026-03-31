"""marketplace_seller_profiles, ai_budget_event_audit, ai_agent_entitlements (RLS).

Revision ID: 0010_seller_ai_entitlements
Revises: 0009_ai_inference
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010_seller_ai_entitlements"
down_revision = "0009_ai_inference"
branch_labels = None
depends_on = None

_TABLES = (
    "marketplace_seller_profiles",
    "ai_budget_event_audit",
    "ai_agent_entitlements",
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
            CREATE TABLE IF NOT EXISTS marketplace_seller_profiles (
                id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status VARCHAR(32) NOT NULL DEFAULT 'verified',
                verified_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (tenant_id, user_id)
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_mkt_seller_profiles_tenant "
            "ON marketplace_seller_profiles (tenant_id)"
        )
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS ai_budget_event_audit (
                id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                budget_id UUID NOT NULL REFERENCES crypto_agent_budgets(id) ON DELETE CASCADE,
                user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                delta_lamports BIGINT NOT NULL,
                allocated_after BIGINT NOT NULL,
                ceiling_lamports BIGINT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_ai_budget_audit_tenant "
            "ON ai_budget_event_audit (tenant_id)"
        )
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS ai_agent_entitlements (
                id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                buyer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                purchase_id UUID NOT NULL REFERENCES marketplace_purchases(id) ON DELETE CASCADE,
                listing_id UUID NOT NULL REFERENCES marketplace_listings(id) ON DELETE CASCADE,
                license_key_sha256 VARCHAR(64) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (tenant_id, purchase_id)
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_ai_agent_ent_buyer "
            "ON ai_agent_entitlements (tenant_id, buyer_id)"
        )
    )

    for t in _TABLES:
        _enable_rls(t)


def downgrade() -> None:
    for table in reversed(_TABLES):
        for pol in (
            "tenant_isolation_select",
            "tenant_isolation_insert",
            "tenant_isolation_update",
            "tenant_isolation_delete",
        ):
            op.execute(sa.text(f'DROP POLICY IF EXISTS {pol} ON "{table}"'))
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{table}"'))
