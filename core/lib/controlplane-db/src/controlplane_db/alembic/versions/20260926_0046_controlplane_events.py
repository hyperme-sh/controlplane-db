"""Postgres-backed control plane event bus.

Revision ID: 0046_controlplane_events
Revises: 0045_lease_failed_at

``controlplane_events`` is the log. A row's delivery records are inserted in
the same transaction by ``deliver_controlplane_event``, for every registered
consumer group that handles that event type. There is no cursor fan-out:
ids are assigned before commit, so a MAX(id) scan can skip a row that commits
later.

Delivery is at-least-once. ``claim_controlplane_event_deliveries`` takes rows
with ``FOR UPDATE SKIP LOCKED``. A handler failure returns the row to
``pending`` with backoff until ``attempts`` reaches ``max_attempts``, then
``dead``. An expired lease whose ``attempts`` are already at ``max_attempts``
is marked ``dead`` instead of being claimed again. A crashed worker loses its
lease and another worker can claim the same row while attempts remain.

Pollers connect with the service ``DATABASE_URL``. Compose uses the
``controlplane`` role (``POSTGRES_USER``). A ``NOBYPASSRLS`` deployment uses
``controlplane_app``. This migration grants those roles, when they exist,
and revokes the event tables, sequence, and functions from ``PUBLIC``.
The insert triggers and ``register_controlplane_event_consumer`` are
``SECURITY DEFINER`` (owner is the migration role, ``search_path`` is
``public``). A publisher only needs ``INSERT`` on ``controlplane_events``
plus ``EXECUTE`` on the trigger functions. Registration takes ``SHARE``,
which requires ``UPDATE``, ``DELETE``, or ``TRUNCATE`` that
``controlplane_app`` does not have, so that function runs as its owner.
``EXECUTE`` stays granted only to the app roles. Pollers need
``SELECT``/``UPDATE`` on ``controlplane_event_deliveries`` and ``EXECUTE``
on ``claim`` / ``register`` / ``replay``. A new group waits at most two
seconds for that lock; the consumer retries on the next poll.

RLS: these tables are platform-scoped. Consumers must see every tenant, and a
publisher often runs with ``app.current_tenant_id`` already set for the business
write. The policy is therefore ``USING (true) WITH CHECK (true)`` under
``FORCE ROW LEVEL SECURITY``. It does not consult the tenant GUC. Superusers
and ``BYPASSRLS`` roles skip RLS entirely; a ``NOBYPASSRLS`` role such as
``controlplane_app`` is covered by this policy and does not need a second GUC.
Do not replace it with the tenant-isolation policy or the outbox insert will
fail whenever the envelope tenant and the session GUC disagree.

Retention: ``prune_controlplane_events(interval)`` deletes an event older than
the interval when it has no delivery rows, or when every delivery is
``delivered`` or ``dead``. A group that is still ``pending`` or ``claimed``
holds the event. A group that registers later only receives events still
inside the window. Default window is 30 days. payment-service runs it daily
when ``CONTROLPLANE_EVENTS_PRUNE_ENABLED`` is set.

There is no per-tenant ordering guarantee. Handlers must not rely on order.

Inserts ``NOTIFY controlplane_events``. Pollers may ``LISTEN``; they must also
poll, because a missed notification is not a missed row.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0046_controlplane_events"
down_revision = "0045_lease_failed_at"
branch_labels = None
depends_on = None

_EVENTS = "controlplane_events"
_SUBSCRIPTIONS = "controlplane_event_subscriptions"
_DELIVERIES = "controlplane_event_deliveries"

_APP_ROLES = ("controlplane", "controlplane_app")

_FUNCTIONS = (
    "notify_controlplane_event()",
    "deliver_controlplane_event()",
    "register_controlplane_event_consumer(text, text[], text, integer)",
    "claim_controlplane_event_deliveries(text, text, integer, integer, bigint[])",
    "replay_controlplane_event_deliveries(text, bigint)",
    "prune_controlplane_events(interval)",
)


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
        _SUBSCRIPTIONS,
        sa.Column("consumer_group", sa.Text(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.PrimaryKeyConstraint("consumer_group", "event_type"),
        sa.CheckConstraint(
            "max_attempts >= 1",
            name="ck_controlplane_event_subscriptions_attempts",
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

    for table in (_EVENTS, _SUBSCRIPTIONS, _DELIVERIES):
        _platform_bus_rls(table)

    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION notify_controlplane_event()
            RETURNS trigger
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = public
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
            CREATE OR REPLACE FUNCTION deliver_controlplane_event()
            RETURNS trigger
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = public
            AS $fn$
            BEGIN
                INSERT INTO controlplane_event_deliveries (
                    event_id, consumer_group, status, attempts, max_attempts, available_at
                )
                SELECT NEW.id, s.consumer_group, 'pending', 0, s.max_attempts, now()
                FROM controlplane_event_subscriptions AS s
                WHERE s.event_type = NEW.event_type
                ON CONFLICT (consumer_group, event_id) DO NOTHING;
                RETURN NEW;
            END;
            $fn$
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER controlplane_events_deliver
            AFTER INSERT ON controlplane_events
            FOR EACH ROW
            EXECUTE FUNCTION deliver_controlplane_event()
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION register_controlplane_event_consumer(
                p_group text,
                p_event_types text[],
                p_mode text,
                p_max_attempts integer
            ) RETURNS void
            LANGUAGE plpgsql
            SECURITY DEFINER
            SET search_path = public
            AS $fn$
            DECLARE
                v_type text;
                v_new boolean;
            BEGIN
                SELECT EXISTS (
                    SELECT 1
                    FROM unnest(p_event_types) AS t(event_type)
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM controlplane_event_subscriptions AS s
                        WHERE s.consumer_group = p_group
                          AND s.event_type = t.event_type
                    )
                ) INTO v_new;

                -- An open insert holds ROW EXCLUSIVE. SHARE waits until that
                -- insert commits, then holds new inserts until this subscription
                -- and its backfill commit. Otherwise the trigger misses the
                -- subscription and the backfill misses the insert. SHARE needs
                -- UPDATE, DELETE, or TRUNCATE, which the app role lacks, so
                -- this function is SECURITY DEFINER. Two seconds is enough for
                -- a commit in flight; a longer publisher transaction fails this
                -- call and the consumer retries on the next poll.
                IF v_new THEN
                    SET LOCAL lock_timeout = '2s';
                    LOCK TABLE controlplane_events IN SHARE MODE;
                END IF;

                FOREACH v_type IN ARRAY p_event_types LOOP
                    INSERT INTO controlplane_event_subscriptions (
                        consumer_group, event_type, max_attempts
                    )
                    VALUES (p_group, v_type, p_max_attempts)
                    ON CONFLICT (consumer_group, event_type) DO UPDATE
                    SET max_attempts = EXCLUDED.max_attempts;
                END LOOP;

                IF p_mode = 'earliest' THEN
                    INSERT INTO controlplane_event_deliveries (
                        event_id, consumer_group, status, attempts, max_attempts, available_at
                    )
                    SELECT e.id, p_group, 'pending', 0, p_max_attempts, now()
                    FROM controlplane_events AS e
                    WHERE e.event_type = ANY (p_event_types)
                    ON CONFLICT (consumer_group, event_id) DO NOTHING;
                END IF;
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
                p_lease_seconds integer,
                p_exclude bigint[] DEFAULT ARRAY[]::bigint[]
            ) RETURNS TABLE (event_id bigint, attempts integer, envelope jsonb)
            LANGUAGE plpgsql
            AS $fn$
            BEGIN
                UPDATE controlplane_event_deliveries AS expired
                SET status = 'dead',
                    claimed_by = NULL,
                    lease_expires_at = NULL,
                    last_error = COALESCE(expired.last_error, 'lease expired after max attempts'),
                    updated_at = now()
                WHERE expired.consumer_group = p_group
                  AND expired.status = 'claimed'
                  AND expired.lease_expires_at <= now()
                  AND expired.attempts >= expired.max_attempts;

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
                      AND q.event_id <> ALL (COALESCE(p_exclude, ARRAY[]::bigint[]))
                      AND (
                        (q.status = 'pending' AND q.available_at <= now())
                        OR (
                            q.status = 'claimed'
                            AND q.lease_expires_at <= now()
                            AND q.attempts < q.max_attempts
                        )
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
            CREATE OR REPLACE FUNCTION replay_controlplane_event_deliveries(
                p_group text,
                p_after_event_id bigint
            ) RETURNS void
            LANGUAGE plpgsql
            AS $fn$
            BEGIN
                UPDATE controlplane_event_deliveries
                SET status = 'pending',
                    attempts = 0,
                    available_at = now(),
                    claimed_by = NULL,
                    claimed_at = NULL,
                    lease_expires_at = NULL,
                    last_error = NULL,
                    delivered_at = NULL,
                    updated_at = now()
                WHERE consumer_group = p_group
                  AND event_id > p_after_event_id;

                INSERT INTO controlplane_event_deliveries (
                    event_id, consumer_group, status, attempts, max_attempts, available_at
                )
                SELECT e.id, s.consumer_group, 'pending', 0, s.max_attempts, now()
                FROM controlplane_events AS e
                JOIN controlplane_event_subscriptions AS s
                  ON s.consumer_group = p_group
                 AND s.event_type = e.event_type
                WHERE e.id > p_after_event_id
                ON CONFLICT (consumer_group, event_id) DO NOTHING;
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

    for signature in _FUNCTIONS:
        op.execute(sa.text(f"REVOKE ALL ON FUNCTION {signature} FROM PUBLIC"))
    op.execute(
        sa.text(
            """
            REVOKE ALL ON TABLE
                controlplane_events,
                controlplane_event_subscriptions,
                controlplane_event_deliveries
            FROM PUBLIC
            """
        )
    )
    op.execute(sa.text("REVOKE ALL ON SEQUENCE controlplane_events_id_seq FROM PUBLIC"))
    op.execute(
        sa.text(
            """
            DO $grant$
            DECLARE
                role_name text;
            BEGIN
                FOREACH role_name IN ARRAY ARRAY['controlplane', 'controlplane_app']
                LOOP
                    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
                        EXECUTE format(
                            'GRANT SELECT, INSERT ON controlplane_events TO %I',
                            role_name
                        );
                        EXECUTE format(
                            'GRANT USAGE, SELECT ON SEQUENCE controlplane_events_id_seq TO %I',
                            role_name
                        );
                        EXECUTE format(
                            'GRANT SELECT, INSERT, UPDATE, DELETE ON controlplane_event_subscriptions TO %I',
                            role_name
                        );
                        EXECUTE format(
                            'GRANT SELECT, INSERT, UPDATE, DELETE ON controlplane_event_deliveries TO %I',
                            role_name
                        );
                        EXECUTE format(
                            'GRANT EXECUTE ON FUNCTION
                                notify_controlplane_event(),
                                deliver_controlplane_event(),
                                register_controlplane_event_consumer(text, text[], text, integer),
                                claim_controlplane_event_deliveries(text, text, integer, integer, bigint[]),
                                replay_controlplane_event_deliveries(text, bigint),
                                prune_controlplane_events(interval)
                             TO %I',
                            role_name
                        );
                    END IF;
                END LOOP;
            END
            $grant$
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP TRIGGER IF EXISTS controlplane_events_deliver ON controlplane_events"))
    op.execute(sa.text("DROP TRIGGER IF EXISTS controlplane_events_notify ON controlplane_events"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS prune_controlplane_events(interval)"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS replay_controlplane_event_deliveries(text, bigint)"))
    op.execute(
        sa.text(
            "DROP FUNCTION IF EXISTS claim_controlplane_event_deliveries(text, text, integer, integer, bigint[])"
        )
    )
    op.execute(
        sa.text(
            "DROP FUNCTION IF EXISTS register_controlplane_event_consumer(text, text[], text, integer)"
        )
    )
    op.execute(sa.text("DROP FUNCTION IF EXISTS deliver_controlplane_event()"))
    op.execute(sa.text("DROP FUNCTION IF EXISTS notify_controlplane_event()"))
    op.drop_table(_DELIVERIES)
    op.drop_table(_SUBSCRIPTIONS)
    op.drop_table(_EVENTS)
