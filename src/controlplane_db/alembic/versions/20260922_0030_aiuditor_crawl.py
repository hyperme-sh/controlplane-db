"""Daily crawl candidates + admission size_bytes.

Revision ID: 0030_aiuditor_crawl
Revises: 0029_aiuditor_program

Metadata-only crawl pins (repo/revision/file/size/license/quant). Weights stay
off the plane. Admission size_bytes supports the static gate.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0030_aiuditor_crawl"
down_revision = "0029_aiuditor_program"
branch_labels = None
depends_on = None


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
            "ALTER TABLE aiuditor_admissions "
            "ADD COLUMN IF NOT EXISTS size_bytes INTEGER"
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS aiuditor_candidates (
                id UUID PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                repo VARCHAR(256) NOT NULL,
                revision VARCHAR(128) NOT NULL,
                file_name VARCHAR(256) NOT NULL,
                size_bytes INTEGER NOT NULL,
                license VARCHAR(64),
                quant VARCHAR(32),
                file_hash VARCHAR(256),
                publisher VARCHAR(64) NOT NULL,
                catalog_id VARCHAR(64) NOT NULL,
                class_id VARCHAR(64) NOT NULL,
                status VARCHAR(16) NOT NULL,
                soak_job_id VARCHAR(64),
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                CONSTRAINT uq_aiuditor_candidate_source_class
                    UNIQUE (tenant_id, repo, revision, file_name, class_id)
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_aiuditor_candidates_tenant "
            "ON aiuditor_candidates (tenant_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_aiuditor_candidates_tenant_class "
            "ON aiuditor_candidates (tenant_id, class_id)"
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_aiuditor_candidates_tenant_status "
            "ON aiuditor_candidates (tenant_id, status)"
        )
    )
    _enable_rls("aiuditor_candidates")


def downgrade() -> None:
    for pol in (
        "tenant_isolation_select",
        "tenant_isolation_insert",
        "tenant_isolation_update",
        "tenant_isolation_delete",
    ):
        op.execute(sa.text(f'DROP POLICY IF EXISTS {pol} ON "aiuditor_candidates"'))
    op.execute(sa.text("DROP TABLE IF EXISTS aiuditor_candidates"))
    op.execute(
        sa.text("ALTER TABLE aiuditor_admissions DROP COLUMN IF EXISTS size_bytes")
    )
