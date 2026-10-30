"""marketplace_listings and marketplace_purchases (RLS).

Revision ID: 0008_marketplace
Revises: 0007_crypto_bdg
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_marketplace"
down_revision = "0007_crypto_bdg"
branch_labels = None
depends_on = None

_TABLES = ("marketplace_listings", "marketplace_purchases")


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
            CREATE TABLE IF NOT EXISTS marketplace_listings (
                id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                seller_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title VARCHAR(512) NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                listing_type VARCHAR(32) NOT NULL,
                price_type VARCHAR(32) NOT NULL,
                price_amount INTEGER,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                is_public BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_marketplace_listings_tenant "
            "ON marketplace_listings (tenant_id)"
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS marketplace_purchases (
                id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                listing_id UUID NOT NULL REFERENCES marketplace_listings(id) ON DELETE CASCADE,
                buyer_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                status VARCHAR(32) NOT NULL,
                license_key VARCHAR(512),
                billing_record_id UUID REFERENCES billing_records(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
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
        op.execute(sa.text(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY'))
        op.execute(sa.text(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY'))
    op.execute(sa.text("DROP TABLE IF EXISTS marketplace_purchases"))
    op.execute(sa.text("DROP TABLE IF EXISTS marketplace_listings"))
