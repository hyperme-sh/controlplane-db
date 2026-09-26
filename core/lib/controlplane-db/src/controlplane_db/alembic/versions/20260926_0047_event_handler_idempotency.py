"""Idempotency keys for redelivered control-plane handlers.

Revision ID: 0047_event_handler_idempotency
Revises: 0046_controlplane_events

``acl_casbin_rules`` rejects a second copy of the same policy tuple.
``ai_budget_event_audit.source_event_id`` is the bus event id, so a
redelivered ``budget.allocated.v1`` inserts once.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0047_event_handler_idempotency"
down_revision = "0046_controlplane_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 0001 create_all already includes columns and indexes that exist on the
    # current models. IF NOT EXISTS keeps a fresh database and a create_all
    # database on the same revision.
    # Identical policy rows already exist in some databases. NULLS NOT DISTINCT
    # treats those NULLs as equal, so the unique index cannot be created until
    # the extras are gone. Keep the lowest id in each group.
    op.execute(
        sa.text(
            """
            DELETE FROM acl_casbin_rules AS r
            WHERE r.id <> (
                SELECT MIN(k.id)
                FROM acl_casbin_rules AS k
                WHERE k.tenant_id IS NOT DISTINCT FROM r.tenant_id
                  AND k.ptype IS NOT DISTINCT FROM r.ptype
                  AND k.v0 IS NOT DISTINCT FROM r.v0
                  AND k.v1 IS NOT DISTINCT FROM r.v1
                  AND k.v2 IS NOT DISTINCT FROM r.v2
                  AND k.v3 IS NOT DISTINCT FROM r.v3
                  AND k.v4 IS NOT DISTINCT FROM r.v4
                  AND k.v5 IS NOT DISTINCT FROM r.v5
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_acl_casbin_rules_identity
            ON acl_casbin_rules (tenant_id, ptype, v0, v1, v2, v3, v4, v5)
            NULLS NOT DISTINCT
            """
        )
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE ai_budget_event_audit
            ADD COLUMN IF NOT EXISTS source_event_id BIGINT
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_budget_event_audit_source_event
            ON ai_budget_event_audit (source_event_id)
            """
        )
    )
    op.execute(
        sa.text(
            """
            ALTER TABLE ai_budget_event_audit
            ADD COLUMN IF NOT EXISTS source_event_key VARCHAR(128)
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uq_ai_budget_event_audit_source_key
            ON ai_budget_event_audit (source_event_key)
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS uq_ai_budget_event_audit_source_key"))
    op.execute(sa.text("ALTER TABLE ai_budget_event_audit DROP COLUMN IF EXISTS source_event_key"))
    op.drop_index("uq_ai_budget_event_audit_source_event", table_name="ai_budget_event_audit")
    op.drop_column("ai_budget_event_audit", "source_event_id")
    op.execute(sa.text("DROP INDEX IF EXISTS uq_acl_casbin_rules_identity"))
