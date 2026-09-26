"""Postgres-backed control plane event bus.

Revision ID: 0045_controlplane_events
Revises: 0044_pricing_schema

``controlplane_events`` is the log. Each consumer group copies new ids into
``controlplane_event_deliveries`` and claims them with ``FOR UPDATE SKIP LOCKED``.
Delivery is at-least-once: a handler failure returns the row to ``pending`` with
backoff until ``attempts`` reaches ``max_attempts``, then ``dead``. A crashed
worker loses its lease and another worker can claim the same row.

RLS: these tables are platform-scoped. Consumers must see every tenant, and a
publisher often runs with ``app.current_tenant_id`` already set for the business
write. The policy is therefore ``USING (true) WITH CHECK (true)`` under
``FORCE ROW LEVEL SECURITY``. It does not consult the tenant GUC. Superusers
and ``BYPASSRLS`` roles skip RLS entirely; a ``NOBYPASSRLS`` role such as
``controlplane_app`` is covered by this policy and does not need a second GUC.
Do not replace it with the tenant-isolation policy or the outbox insert will
fail whenever the envelope tenant and the session GUC disagree.

Retention: ``prune_controlplane_events(interval)`` deletes events older than the
interval whose deliveries are all terminal (``delivered`` or ``dead``), and
events that were never copied into a delivery. Default window is 30 days.
Call it from a scheduler. A consumer group that stays offline longer than the
window misses those events; reset the cursor only within the retained log.

Inserts ``NOTIFY controlplane_events``. Pollers may ``LISTEN``; they must also
poll, because a missed notification is not a missed row.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0045_controlplane_events"
down_revision = "0044_pricing_schema"
branch_labels = None
depends_on = None

_EVENTS = "controlplane_events"
_CURSORS = "controlplane_event_cursors"
_DELIVERIES = "controlplane_event_deliveries"


def _platform_bus_rls(table: str) -> None:
    """Readable and writable with or without app.current_tenant_id."""

    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f"""
            CREATE POLICY platform_bus_all ON "{table}"
            FOR ALL
            USING (true)
            WITH CHECK (true)
            """
        )
    )


def upgrade() -> None:
    op.create_table(
        _EVENTS,
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=True),
        sa.Column("envelope", JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_controlplane_events_created_at", _EVENTS, ["created_at"])
    op.create_index("ix_controlplane_events_type_id", _EVENTS, ["event_type", "id"])

    op.create_table(
        _CURSORS,
        sa.Column("consumer_group", sa.Text(), primary_key=True),
        sa.Column("last_event_id", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_table(
        _DELIVERIES,
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("consumer_group", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("claimed_by", sa.Text(), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["event_id"], [f"{_EVENTS}.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("consumer_group", "event_id"),
        sa.CheckConstraint(
            "status IN ('pending', 'claimed', 'delivered', 'dead')",
            name="ck_controlplane_event_deliveries_status",
        ),
        sa.CheckConstraint(
            "attempts >= 0 AND max_attempts >= 1",
            name="ck_controlplane_event_deliveries_attempts",
        ),
    )
    op.create_index(
        "ix_controlplane_event_deliveries_pending",
        _DELIVERIES,
        ["consumer_group", "available_at", "event_id"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "ix_controlplane_event_deliveries_claimed",
        _DELIVERIES,
        ["consumer_group", "lease_expires_at"],
        postgresql_where=sa.text("status = 'claimed'"),
    )

    for table in (_EVENTS, _CURSORS, _DELIVERIES):
        _platform_bus_rls(table)

    op.execute(
        sa.text(
            """
            GRANT SELECT, INSERT, UPDATE, DELETE
            ON controlplane_events, controlplane_event_cursors, controlplane_event_deliveries
            TO PUBLIC
            """
        )
    )
    op.execute(
        sa.text(
            "GRANT USAGE, SELECT ON SEQUENCE controlplane_events_id_seq TO PUBLIC"
        )
    )

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION notify_controlplane_event()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $fn$
            BEGIN
                PERFORM pg_notify('controlplane_events', NEW.id::text);
                RETURN NEW;
            END;
            $fn$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER controlplane_events_notify
            AFTER INSERT ON controlplane_events
            FOR EACH ROW
            EXECUTE FUNCTION notify_controlplane_event()
            """
        )
    )

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION ensure_controlplane_event_cursor(
                p_group text,
                p_mode text
            ) RETURNS void
            LANGUAGE plpgsql
            AS $fn$
            DECLARE
                v_start bigint;
            BEGIN
                IF p_mode = 'latest' THEN
                    SELECT COALESCE(MAX(id), 0) INTO v_start FROM controlplane_events;
                ELSE
                    v_start := 0;
                END IF;
                INSERT INTO controlplane_event_cursors (consumer_group, last_event_id)
                VALUES (p_group, v_start)
                ON CONFLICT (consumer_group) DO NOTHING;
            END;
            $fn$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION fanout_controlplane_event_deliveries(
                p_group text,
                p_max_attempts integer
            ) RETURNS integer
            LANGUAGE plpgsql
            AS $fn$
            DECLARE
                v_cursor bigint;
                v_max bigint;
                v_inserted integer;
            BEGIN
                PERFORM ensure_controlplane_event_cursor(p_group, 'earliest');

                SELECT last_event_id INTO v_cursor
                FROM controlplane_event_cursors
                WHERE consumer_group = p_group
                FOR UPDATE;

                SELECT COALESCE(MAX(id), v_cursor) INTO v_max FROM controlplane_events;

                INSERT INTO controlplane_event_deliveries (
                    event_id, consumer_group, status, attempts, max_attempts, available_at
                )
                SELECT e.id, p_group, 'pending', 0, p_max_attempts, now()
                FROM controlplane_events e
                WHERE e.id > v_cursor
                ON CONFLICT (consumer_group, event_id) DO NOTHING;

                GET DIAGNOSTICS v_inserted = ROW_COUNT;

                UPDATE controlplane_event_cursors
                SET last_event_id = v_max,
                    updated_at = now()
                WHERE consumer_group = p_group;

                RETURN v_inserted;
            END;
            $fn$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION claim_controlplane_event_deliveries(
                p_group text,
                p_worker text,
                p_limit integer,
                p_lease_seconds integer
            ) RETURNS TABLE (event_id bigint, attempts integer, envelope jsonb)
            LANGUAGE plpgsql
            AS $fn$
            BEGIN
                RETURN QUERY
                UPDATE controlplane_event_deliveries AS d
                SET status = 'claimed',
                    claimed_by = p_worker,
                    claimed_at = now(),
                    lease_expires_at = now() + make_interval(secs => p_lease_seconds),
                    attempts = d.attempts + 1,
                    updated_at = now()
                FROM (
                    SELECT q.event_id
                    FROM controlplane_event_deliveries AS q
                    WHERE q.consumer_group = p_group
                      AND (
                        (q.status = 'pending' AND q.available_at <= now())
                        OR (q.status = 'claimed' AND q.lease_expires_at <= now())
                      )
                    ORDER BY q.event_id
                    FOR UPDATE SKIP LOCKED
                    LIMIT p_limit
                ) AS picked
                WHERE d.consumer_group = p_group
                  AND d.event_id = picked.event_id
                RETURNING d.event_id, d.attempts, (
                    SELECT e.envelope FROM controlplane_events AS e WHERE e.id = d.event_id
                );
            END;
            $fn$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION reset_controlplane_event_cursor(
                p_group text,
                p_last_event_id bigint
            ) RETURNS void
            LANGUAGE plpgsql
            AS $fn$
            BEGIN
                INSERT INTO controlplane_event_cursors (consumer_group, last_event_id)
                VALUES (p_group, p_last_event_id)
                ON CONFLICT (consumer_group) DO UPDATE
                SET last_event_id = EXCLUDED.last_event_id,
                    updated_at = now();

                DELETE FROM controlplane_event_deliveries
                WHERE consumer_group = p_group
                  AND event_id > p_last_event_id;
            END;
            $fn$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION prune_controlplane_events(retention interval)
            RETURNS bigint
            LANGUAGE plpgsql
            AS $fn$
            DECLARE
                removed bigint;
            BEGIN
                DELETE FROM controlplane_events AS e
                WHERE e.created_at < now() - retention
                  AND NOT EXISTS (
                    SELECT 1
                    FROM controlplane_event_deliveries AS d
                    WHERE d.event_id = e.id
                      AND d.status NOT IN ('delivered', 'dead')
                  );
                GET DIAGNOSTICS removed = ROW_COUNT;
                RETURN removed;
            END;
            $fn$
            """
        )
    )
    op.execute(
        sa.text(
            """
            GRANT EXECUTE ON FUNCTION
                notify_controlplane_event(),
                ensure_controlplane_event_cursor(text, text),
                fanout_controlplane_event_deliveries(text, integer),
                claim_controlplane_event_deliveries(text, text, integer, integer),
                reset_controlplane_event_cursor(text, bigint),
                prune_controlplane_events(interval)
            TO PUBLIC
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS controlplane_events_notify ON controlplane_events"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS prune_controlplane_events(interval)"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS reset_controlplane_event_cursor(text, bigint)"))
    op.execute(
        sa.text(
            "DROP FUNCTION IF EXISTS claim_controlplane_event_deliveries(text, text, integer, integer)"
        )
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS fanout_controlplane_event_deliveries(text, integer)"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS ensure_controlplane_event_cursor(text, text)"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS notify_controlplane_event()"))
    op.drop_table(_DELIVERIES)
    op.drop_table(_CURSORS)
    op.drop_table(_EVENTS)
