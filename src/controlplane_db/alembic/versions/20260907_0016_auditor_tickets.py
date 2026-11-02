"""Hypermesh fyber.auditor tickets (plane inbox + resolution intent).

Revision ID: 0016_auditor_tickets
Revises: 0015_site_machine_tokens
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0016_auditor_tickets"
down_revision = "0015_site_machine_tokens"
branch_labels = None
depends_on = None

_TABLE = "hypermesh_auditor_tickets"


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
                ticket_id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                site_id VARCHAR(128) NOT NULL,
                ticket_schema VARCHAR(64) NOT NULL,
                trace_id UUID NOT NULL,
                receipt_id UUID,
                held_call_id UUID NOT NULL,
                reason_code VARCHAR(64) NOT NULL,
                severity VARCHAR(16) NOT NULL,
                text_redacted VARCHAR(1000) NOT NULL,
                display JSONB NOT NULL,
                status VARCHAR(16) NOT NULL,
                resolution VARCHAR(16),
                resolved_by VARCHAR(256),
                resolved_at TIMESTAMPTZ,
                patch JSONB,
                notes_redacted VARCHAR(1000),
                site_acked_receipt_id UUID,
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )
    )
    op.execute(
        sa.text(f"CREATE INDEX IF NOT EXISTS ix_hm_auditor_tickets_tenant ON {_TABLE} (tenant_id)")
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_hm_auditor_tickets_tenant_site "
            f"ON {_TABLE} (tenant_id, site_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_hm_auditor_tickets_receipt "
            f"ON {_TABLE} (tenant_id, site_id, receipt_id) "
            "WHERE receipt_id IS NOT NULL"
        )
    )
    op.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_hm_auditor_tickets_trace_reason "
            f"ON {_TABLE} (tenant_id, site_id, trace_id, reason_code) "
            "WHERE receipt_id IS NULL"
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
