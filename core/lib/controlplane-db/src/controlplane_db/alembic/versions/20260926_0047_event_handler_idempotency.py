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


def downgrade() -> None:
    op.drop_index("uq_ai_budget_event_audit_source_event", table_name="ai_budget_event_audit")
    op.drop_column("ai_budget_event_audit", "source_event_id")
    op.execute(sa.text("DROP INDEX IF EXISTS uq_acl_casbin_rules_identity"))
