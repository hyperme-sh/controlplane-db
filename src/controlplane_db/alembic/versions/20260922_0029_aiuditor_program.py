"""AIuditor model cert program tables: envelopes, suite, admissions.

Revision ID: 0029_aiuditor_program
Revises: 0028_device_lab

Class envelopes, core cert suite membership, and uploaded-model admission
verdicts. Hypermesh stays scorecards, leases, and catalog stamps. Prompt
bodies and HMAC blobs stay off these tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0029_aiuditor_program"
down_revision = "0028_device_lab"
branch_labels = None
depends_on = None

_TABLES = (
    "aiuditor_envelopes",
    "aiuditor_suite_members",
    "aiuditor_admissions",
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
            CREATE TABLE IF NOT EXISTS aiuditor_envelopes (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                class_id VARCHAR(64) NOT NULL,
                catalog_id VARCHAR(64) NOT NULL,
                file_hash VARCHAR(256) NOT NULL,
                quant VARCHAR(32),
                runtime VARCHAR(64) NOT NULL,
                context INTEGER,
                fit BOOLEAN NOT NULL DEFAULT TRUE,
                decode_tok_s DOUBLE PRECISION,
                thermal_c DOUBLE PRECISION,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                CONSTRAINT uq_aiuditor_envelope_class_catalog
                    UNIQUE (tenant_id, class_id, catalog_id)
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_aiuditor_envelopes_tenant "
            "ON aiuditor_envelopes (tenant_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_aiuditor_envelopes_tenant_class "
            "ON aiuditor_envelopes (tenant_id, class_id)"
        )
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS aiuditor_suite_members (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                class_id VARCHAR(64) NOT NULL,
                catalog_id VARCHAR(64) NOT NULL,
                pack_id VARCHAR(64) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                CONSTRAINT uq_aiuditor_suite_class_catalog
                    UNIQUE (tenant_id, class_id, catalog_id)
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_aiuditor_suite_members_tenant "
            "ON aiuditor_suite_members (tenant_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_aiuditor_suite_members_tenant_class "
            "ON aiuditor_suite_members (tenant_id, class_id)"
        )
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS aiuditor_admissions (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                file_hash VARCHAR(256) NOT NULL,
                format VARCHAR(32) NOT NULL,
                quant VARCHAR(32),
                license VARCHAR(64) NOT NULL,
                intended_class VARCHAR(64) NOT NULL,
                credential_ref VARCHAR(128),
                status VARCHAR(16) NOT NULL,
                verdict VARCHAR(16),
                reason VARCHAR(120),
                resolved_by VARCHAR(256),
                created_at TIMESTAMPTZ NOT NULL,
                resolved_at TIMESTAMPTZ
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_aiuditor_admissions_tenant "
            "ON aiuditor_admissions (tenant_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_aiuditor_admissions_tenant_status "
            "ON aiuditor_admissions (tenant_id, status)"
        )
    )

    for table in _TABLES:
        _enable_rls(table)


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
