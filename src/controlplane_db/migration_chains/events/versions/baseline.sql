-- Frozen schema-only baseline at 0053_onboarding_runs. No seed data.
SET LOCAL search_path = public, pg_catalog;
SET LOCAL check_function_bodies = false;

-- FUNCTION: claim_controlplane_event_deliveries(text, text, integer, integer, bigint[])
CREATE FUNCTION public.claim_controlplane_event_deliveries(p_group text, p_worker text, p_limit integer, p_lease_seconds integer, p_exclude bigint[] DEFAULT ARRAY[]::bigint[]) RETURNS TABLE(event_id bigint, attempts integer, envelope jsonb)
    LANGUAGE plpgsql
    AS $$
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
            $$;


--

-- FUNCTION: deliver_controlplane_event()
CREATE FUNCTION public.deliver_controlplane_event() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public', 'pg_temp'
    AS $$
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
            $$;


--

-- FUNCTION: notify_controlplane_event()
CREATE FUNCTION public.notify_controlplane_event() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public', 'pg_temp'
    AS $$
            BEGIN
                PERFORM pg_notify('controlplane_events', NEW.id::text);
                RETURN NEW;
            END;
            $$;


--

-- FUNCTION: prune_controlplane_events(interval)
CREATE FUNCTION public.prune_controlplane_events(retention interval) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
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
            $$;


--

-- FUNCTION: register_controlplane_event_consumer(text, text[], text, integer)
CREATE FUNCTION public.register_controlplane_event_consumer(p_group text, p_event_types text[], p_mode text, p_max_attempts integer) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'pg_catalog', 'public', 'pg_temp'
    AS $$
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
            $$;


--

-- FUNCTION: replay_controlplane_event_deliveries(text, bigint)
CREATE FUNCTION public.replay_controlplane_event_deliveries(p_group text, p_after_event_id bigint) RETURNS void
    LANGUAGE plpgsql
    AS $$
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
            $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--

-- TABLE: controlplane_event_deliveries
CREATE TABLE public.controlplane_event_deliveries (
    event_id bigint NOT NULL,
    consumer_group text NOT NULL,
    status text DEFAULT 'pending'::text NOT NULL,
    attempts integer DEFAULT 0 NOT NULL,
    max_attempts integer DEFAULT 5 NOT NULL,
    available_at timestamp with time zone DEFAULT now() NOT NULL,
    claimed_by text,
    claimed_at timestamp with time zone,
    lease_expires_at timestamp with time zone,
    last_error text,
    delivered_at timestamp with time zone,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT ck_controlplane_event_deliveries_attempts CHECK (((attempts >= 0) AND (max_attempts >= 1))),
    CONSTRAINT ck_controlplane_event_deliveries_status CHECK ((status = ANY (ARRAY['pending'::text, 'claimed'::text, 'delivered'::text, 'dead'::text])))
);

ALTER TABLE ONLY public.controlplane_event_deliveries FORCE ROW LEVEL SECURITY;


--

-- TABLE: controlplane_event_subscriptions
CREATE TABLE public.controlplane_event_subscriptions (
    consumer_group text NOT NULL,
    event_type text NOT NULL,
    max_attempts integer DEFAULT 5 NOT NULL,
    CONSTRAINT ck_controlplane_event_subscriptions_attempts CHECK ((max_attempts >= 1))
);

ALTER TABLE ONLY public.controlplane_event_subscriptions FORCE ROW LEVEL SECURITY;


--

-- TABLE: controlplane_events
CREATE TABLE public.controlplane_events (
    id bigint NOT NULL,
    event_type text NOT NULL,
    tenant_id uuid,
    envelope jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.controlplane_events FORCE ROW LEVEL SECURITY;


--

-- SEQUENCE: controlplane_events_id_seq
CREATE SEQUENCE public.controlplane_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--

-- SEQUENCE OWNED BY: controlplane_events_id_seq
ALTER SEQUENCE public.controlplane_events_id_seq OWNED BY public.controlplane_events.id;


--

-- DEFAULT: controlplane_events id
ALTER TABLE ONLY public.controlplane_events ALTER COLUMN id SET DEFAULT nextval('public.controlplane_events_id_seq'::regclass);


--

-- CONSTRAINT: controlplane_event_deliveries controlplane_event_deliveries_pkey
ALTER TABLE ONLY public.controlplane_event_deliveries
    ADD CONSTRAINT controlplane_event_deliveries_pkey PRIMARY KEY (consumer_group, event_id);


--

-- CONSTRAINT: controlplane_event_subscriptions controlplane_event_subscriptions_pkey
ALTER TABLE ONLY public.controlplane_event_subscriptions
    ADD CONSTRAINT controlplane_event_subscriptions_pkey PRIMARY KEY (consumer_group, event_type);


--

-- CONSTRAINT: controlplane_events controlplane_events_pkey
ALTER TABLE ONLY public.controlplane_events
    ADD CONSTRAINT controlplane_events_pkey PRIMARY KEY (id);


--

-- INDEX: ix_controlplane_event_deliveries_claimed
CREATE INDEX ix_controlplane_event_deliveries_claimed ON public.controlplane_event_deliveries USING btree (consumer_group, lease_expires_at) WHERE (status = 'claimed'::text);


--

-- INDEX: ix_controlplane_event_deliveries_pending
CREATE INDEX ix_controlplane_event_deliveries_pending ON public.controlplane_event_deliveries USING btree (consumer_group, available_at, event_id) WHERE (status = 'pending'::text);


--

-- INDEX: ix_controlplane_events_created_at
CREATE INDEX ix_controlplane_events_created_at ON public.controlplane_events USING btree (created_at);


--

-- INDEX: ix_controlplane_events_type_id
CREATE INDEX ix_controlplane_events_type_id ON public.controlplane_events USING btree (event_type, id);


--

-- TRIGGER: controlplane_events controlplane_events_deliver
CREATE TRIGGER controlplane_events_deliver AFTER INSERT ON public.controlplane_events FOR EACH ROW EXECUTE FUNCTION public.deliver_controlplane_event();


--

-- TRIGGER: controlplane_events controlplane_events_notify
CREATE TRIGGER controlplane_events_notify AFTER INSERT ON public.controlplane_events FOR EACH ROW EXECUTE FUNCTION public.notify_controlplane_event();


--

-- FK CONSTRAINT: controlplane_event_deliveries controlplane_event_deliveries_event_id_fkey
ALTER TABLE ONLY public.controlplane_event_deliveries
    ADD CONSTRAINT controlplane_event_deliveries_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.controlplane_events(id) ON DELETE CASCADE;


--

-- ROW SECURITY: controlplane_event_deliveries
ALTER TABLE public.controlplane_event_deliveries ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: controlplane_event_subscriptions
ALTER TABLE public.controlplane_event_subscriptions ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: controlplane_events
ALTER TABLE public.controlplane_events ENABLE ROW LEVEL SECURITY;

--

-- POLICY: controlplane_event_deliveries platform_bus_all
CREATE POLICY platform_bus_all ON public.controlplane_event_deliveries USING (true) WITH CHECK (true);


--

-- POLICY: controlplane_event_subscriptions platform_bus_all
CREATE POLICY platform_bus_all ON public.controlplane_event_subscriptions USING (true) WITH CHECK (true);


--

-- POLICY: controlplane_events platform_bus_all
CREATE POLICY platform_bus_all ON public.controlplane_events USING (true) WITH CHECK (true);


--

-- ACL: FUNCTION claim_controlplane_event_deliveries(p_group text, p_worker text, p_limit integer, p_lease_seconds integer, p_exclude bigint[])
REVOKE ALL ON FUNCTION public.claim_controlplane_event_deliveries(p_group text, p_worker text, p_limit integer, p_lease_seconds integer, p_exclude bigint[]) FROM PUBLIC;
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane') THEN EXECUTE 'GRANT ALL ON FUNCTION public.claim_controlplane_event_deliveries(p_group text, p_worker text, p_limit integer, p_lease_seconds integer, p_exclude bigint[]) TO controlplane;'; END IF; END $baseline_grant$;
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane_app') THEN EXECUTE 'GRANT ALL ON FUNCTION public.claim_controlplane_event_deliveries(p_group text, p_worker text, p_limit integer, p_lease_seconds integer, p_exclude bigint[]) TO controlplane_app;'; END IF; END $baseline_grant$;


--

-- ACL: FUNCTION deliver_controlplane_event()
REVOKE ALL ON FUNCTION public.deliver_controlplane_event() FROM PUBLIC;
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane') THEN EXECUTE 'GRANT ALL ON FUNCTION public.deliver_controlplane_event() TO controlplane;'; END IF; END $baseline_grant$;
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane_app') THEN EXECUTE 'GRANT ALL ON FUNCTION public.deliver_controlplane_event() TO controlplane_app;'; END IF; END $baseline_grant$;


--

-- ACL: FUNCTION notify_controlplane_event()
REVOKE ALL ON FUNCTION public.notify_controlplane_event() FROM PUBLIC;
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane') THEN EXECUTE 'GRANT ALL ON FUNCTION public.notify_controlplane_event() TO controlplane;'; END IF; END $baseline_grant$;
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane_app') THEN EXECUTE 'GRANT ALL ON FUNCTION public.notify_controlplane_event() TO controlplane_app;'; END IF; END $baseline_grant$;


--

-- ACL: FUNCTION prune_controlplane_events(retention interval)
REVOKE ALL ON FUNCTION public.prune_controlplane_events(retention interval) FROM PUBLIC;
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane') THEN EXECUTE 'GRANT ALL ON FUNCTION public.prune_controlplane_events(retention interval) TO controlplane;'; END IF; END $baseline_grant$;
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane_app') THEN EXECUTE 'GRANT ALL ON FUNCTION public.prune_controlplane_events(retention interval) TO controlplane_app;'; END IF; END $baseline_grant$;


--

-- ACL: FUNCTION register_controlplane_event_consumer(p_group text, p_event_types text[], p_mode text, p_max_attempts integer)
REVOKE ALL ON FUNCTION public.register_controlplane_event_consumer(p_group text, p_event_types text[], p_mode text, p_max_attempts integer) FROM PUBLIC;
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane') THEN EXECUTE 'GRANT ALL ON FUNCTION public.register_controlplane_event_consumer(p_group text, p_event_types text[], p_mode text, p_max_attempts integer) TO controlplane;'; END IF; END $baseline_grant$;
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane_app') THEN EXECUTE 'GRANT ALL ON FUNCTION public.register_controlplane_event_consumer(p_group text, p_event_types text[], p_mode text, p_max_attempts integer) TO controlplane_app;'; END IF; END $baseline_grant$;


--

-- ACL: FUNCTION replay_controlplane_event_deliveries(p_group text, p_after_event_id bigint)
REVOKE ALL ON FUNCTION public.replay_controlplane_event_deliveries(p_group text, p_after_event_id bigint) FROM PUBLIC;
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane') THEN EXECUTE 'GRANT ALL ON FUNCTION public.replay_controlplane_event_deliveries(p_group text, p_after_event_id bigint) TO controlplane;'; END IF; END $baseline_grant$;
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane_app') THEN EXECUTE 'GRANT ALL ON FUNCTION public.replay_controlplane_event_deliveries(p_group text, p_after_event_id bigint) TO controlplane_app;'; END IF; END $baseline_grant$;


--

-- ACL: TABLE controlplane_event_deliveries
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane') THEN EXECUTE 'GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.controlplane_event_deliveries TO controlplane;'; END IF; END $baseline_grant$;
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane_app') THEN EXECUTE 'GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.controlplane_event_deliveries TO controlplane_app;'; END IF; END $baseline_grant$;


--

-- ACL: TABLE controlplane_event_subscriptions
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane') THEN EXECUTE 'GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.controlplane_event_subscriptions TO controlplane;'; END IF; END $baseline_grant$;
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane_app') THEN EXECUTE 'GRANT SELECT,INSERT,DELETE,UPDATE ON TABLE public.controlplane_event_subscriptions TO controlplane_app;'; END IF; END $baseline_grant$;


--

-- ACL: TABLE controlplane_events
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane') THEN EXECUTE 'GRANT SELECT,INSERT ON TABLE public.controlplane_events TO controlplane;'; END IF; END $baseline_grant$;
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane_app') THEN EXECUTE 'GRANT SELECT,INSERT ON TABLE public.controlplane_events TO controlplane_app;'; END IF; END $baseline_grant$;


--

-- ACL: SEQUENCE controlplane_events_id_seq
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane') THEN EXECUTE 'GRANT SELECT,USAGE ON SEQUENCE public.controlplane_events_id_seq TO controlplane;'; END IF; END $baseline_grant$;
DO $baseline_grant$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane_app') THEN EXECUTE 'GRANT SELECT,USAGE ON SEQUENCE public.controlplane_events_id_seq TO controlplane_app;'; END IF; END $baseline_grant$;


--
-- PostgreSQL database dump complete
--
