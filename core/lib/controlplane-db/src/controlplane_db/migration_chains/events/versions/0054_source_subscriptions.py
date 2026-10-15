"""Filter durable subscriptions and historical backfill by envelope source."""

from alembic import op

revision = "events_0054_source_subscriptions"
down_revision = "events_0053_baseline"
branch_labels = None
depends_on = None

_SQL = r"""
ALTER TABLE public.controlplane_event_subscriptions ADD COLUMN source_service text;
CREATE INDEX ix_controlplane_events_type_source_id
    ON public.controlplane_events(event_type, (envelope->>'service'), id);

CREATE FUNCTION public.register_controlplane_event_consumer(
    p_group text, p_event_types text[], p_mode text, p_max_attempts integer,
    p_source_service text
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'public', 'pg_temp'
AS $$
DECLARE
    v_type text;
    v_new boolean;
BEGIN
    IF p_source_service IS NOT NULL AND btrim(p_source_service) = '' THEN
        RAISE EXCEPTION 'source service must be nonempty';
    END IF;
    SET LOCAL lock_timeout = '2s';
    -- Serialize first starts, including attempts to register conflicting filters.
    PERFORM pg_advisory_xact_lock(hashtextextended('event-group:' || p_group, 0));
    IF EXISTS (
        SELECT 1 FROM public.controlplane_event_subscriptions AS s
        WHERE s.consumer_group = p_group
          AND s.source_service IS DISTINCT FROM p_source_service
    ) THEN
        RAISE EXCEPTION 'consumer group source filter cannot change';
    END IF;
    SELECT EXISTS (
        SELECT 1 FROM unnest(p_event_types) AS t(event_type)
        WHERE NOT EXISTS (
            SELECT 1 FROM public.controlplane_event_subscriptions AS s
            WHERE s.consumer_group = p_group AND s.event_type = t.event_type
        )
    ) INTO v_new;

    -- SHARE waits for open inserts, then excludes inserts until the subscription
    -- and its backfill commit together. Otherwise both can miss the same event.
    -- Keep the existing bounded lock wait so consumers can retry registration.
    IF v_new THEN
        LOCK TABLE public.controlplane_events IN SHARE MODE;
    END IF;
    FOREACH v_type IN ARRAY p_event_types LOOP
        INSERT INTO public.controlplane_event_subscriptions (
            consumer_group, event_type, max_attempts, source_service
        ) VALUES (p_group, v_type, p_max_attempts, p_source_service)
        ON CONFLICT (consumer_group, event_type) DO UPDATE
        SET max_attempts = EXCLUDED.max_attempts;
    END LOOP;

    IF p_mode = 'earliest' THEN
        IF p_source_service IS NULL THEN
            INSERT INTO public.controlplane_event_deliveries (
                event_id, consumer_group, status, attempts, max_attempts, available_at
            )
            SELECT e.id, p_group, 'pending', 0, p_max_attempts, now()
            FROM public.controlplane_events AS e
            WHERE e.event_type = ANY (p_event_types)
            ON CONFLICT (consumer_group, event_id) DO NOTHING;
        ELSE
            -- Keep the equality separate from the unfiltered query so PostgreSQL
            -- can use both the event-type and source keys of the new index.
            INSERT INTO public.controlplane_event_deliveries (
                event_id, consumer_group, status, attempts, max_attempts, available_at
            )
            SELECT e.id, p_group, 'pending', 0, p_max_attempts, now()
            FROM public.controlplane_events AS e
            WHERE e.event_type = ANY (p_event_types)
              AND e.envelope->>'service' = p_source_service
            ON CONFLICT (consumer_group, event_id) DO NOTHING;
        END IF;
    END IF;
END;
$$;

-- Old callers cannot change a source filter. Preserve an existing group's
-- filter so an N-1 relay image still registers after the expand-only migration.
-- New unfiltered groups continue using NULL, as before.
CREATE OR REPLACE FUNCTION public.register_controlplane_event_consumer(
    p_group text, p_event_types text[], p_mode text, p_max_attempts integer
) RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'public', 'pg_temp'
AS $$
DECLARE v_source text;
BEGIN
    SET LOCAL lock_timeout = '2s';
    PERFORM pg_advisory_xact_lock(hashtextextended('event-group:' || p_group, 0));
    SELECT s.source_service INTO v_source
    FROM public.controlplane_event_subscriptions AS s
    WHERE s.consumer_group = p_group LIMIT 1;
    PERFORM public.register_controlplane_event_consumer(
        p_group, p_event_types, p_mode, p_max_attempts, v_source
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.deliver_controlplane_event()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path TO 'pg_catalog', 'public', 'pg_temp'
AS $$
BEGIN
    INSERT INTO public.controlplane_event_deliveries (
        event_id, consumer_group, status, attempts, max_attempts, available_at
    )
    SELECT NEW.id, s.consumer_group, 'pending', 0, s.max_attempts, now()
    FROM public.controlplane_event_subscriptions AS s
    WHERE s.event_type = NEW.event_type
      AND (s.source_service IS NULL OR s.source_service = NEW.envelope->>'service')
    ON CONFLICT (consumer_group, event_id) DO NOTHING;
    RETURN NEW;
END;
$$;

-- Narrow an already registered relay in place. Preserve delivery IDs, completion
-- and retry history. Previously queued non-deposits drain through the existing
-- handler's source guard; registration creates no further unrelated deliveries.
UPDATE public.controlplane_event_subscriptions
SET source_service = 'payment-service-deposit-outbox'
WHERE consumer_group = 'payment.deposit.servicebus-outbox.v1'
  AND event_type = 'payment.succeeded.v1'
  AND source_service IS NULL;

REVOKE ALL ON FUNCTION public.register_controlplane_event_consumer(text,text[],text,integer,text) FROM PUBLIC;
DO $grant$
DECLARE role_name text;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['controlplane', 'controlplane_app'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION public.register_controlplane_event_consumer(text,text[],text,integer,text) TO %I', role_name);
        END IF;
    END LOOP;
END $grant$;
"""


def upgrade():
    op.get_bind().exec_driver_sql(_SQL, execution_options={"no_parameters": True})


def downgrade():
    raise RuntimeError("Source subscriptions require a reviewed database restore.")
