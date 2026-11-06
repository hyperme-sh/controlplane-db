"""Operator bans, audit, peers, and the shared mail quota.

Revision ID: 0034_operator_console
Revises: 0033_admission_sandbox

Ban rows are tenant-scoped. One active row per subject. Mail quota is the
account budget (10k/month) and is not tenant-scoped.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0034_operator_console"
down_revision = "0033_admission_sandbox"
branch_labels = None
depends_on = None


def _tenant_policy_sql(table: str, op_name: str) -> str:
    cond = """(
                current_setting('app.current_tenant_id', true) <> ''
                AND tenant_id = current_setting('app.current_tenant_id', true)::uuid
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
            CREATE TABLE IF NOT EXISTS operator_bans (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                subject_kind VARCHAR(16) NOT NULL,
                subject_id UUID NOT NULL,
                reason TEXT NOT NULL,
                created_by VARCHAR(512) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                lifted_at TIMESTAMPTZ,
                lifted_by VARCHAR(512),
                lift_reason TEXT,
                subject_label VARCHAR(512)
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_operator_bans_active
            ON operator_bans (tenant_id, subject_kind, subject_id)
            WHERE lifted_at IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS operator_audit (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                actor VARCHAR(512) NOT NULL,
                action VARCHAR(64) NOT NULL,
                target_kind VARCHAR(32) NOT NULL,
                target_id VARCHAR(64) NOT NULL,
                reason TEXT NOT NULL,
                detail JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS operator_peers (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                display_name VARCHAR(256) NOT NULL,
                base_url VARCHAR(512) NOT NULL,
                peer_tenant_id VARCHAR(64) NOT NULL,
                last_health_ok BOOLEAN NOT NULL,
                last_health_detail VARCHAR(500) NOT NULL,
                checked_at TIMESTAMPTZ NOT NULL
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS operator_mail_quota (
                year_month VARCHAR(7) NOT NULL PRIMARY KEY,
                sent_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
    )
    for table in ("operator_bans", "operator_audit", "operator_peers"):
        _enable_rls(table)


def downgrade() -> None:
    for table in ("operator_peers", "operator_audit", "operator_bans"):
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{table}"'))
    op.execute(sa.text("DROP TABLE IF EXISTS operator_mail_quota"))
