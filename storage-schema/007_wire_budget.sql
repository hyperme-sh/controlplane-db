-- Additive, explicitly installed aggregate company egress accounting.
CREATE TABLE wire_policies (
    tenant_id uuid PRIMARY KEY REFERENCES tenants(id),
    daily_bytes bigint NOT NULL CHECK (daily_bytes BETWEEN 1 AND 32000000000),
    generation uuid NOT NULL CHECK (generation <> '00000000-0000-0000-0000-000000000000'),
    enabled boolean NOT NULL DEFAULT false
);
CREATE TABLE wire_reservations (
    tenant_id uuid NOT NULL REFERENCES wire_policies(tenant_id),
    reservation_id uuid NOT NULL,
    generation uuid NOT NULL,
    consumer uuid NOT NULL,
    purpose text NOT NULL CHECK (purpose IN ('turn','mediamtx')),
    issued_at bigint NOT NULL,
    expires_at bigint NOT NULL,
    reserved_bytes bigint NOT NULL CHECK (reserved_bytes BETWEEN 1 AND 32000000000),
    claimed boolean NOT NULL DEFAULT false,
    PRIMARY KEY (tenant_id,reservation_id),
    CHECK (issued_at >= 0 AND expires_at > issued_at AND expires_at-issued_at <= 60),
    CHECK (issued_at/86400=(expires_at-1)/86400)
);
CREATE INDEX wire_daily_budget ON wire_reservations(tenant_id,issued_at);
CREATE FUNCTION wire_reservation_guard() RETURNS trigger
LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
DECLARE policy record;
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'Wire accounting requires read committed isolation';
    END IF;
    PERFORM id FROM tenants WHERE id=NEW.tenant_id FOR UPDATE;
    SELECT * INTO policy FROM wire_policies WHERE tenant_id=NEW.tenant_id;
    IF NOT FOUND OR NOT policy.enabled OR NEW.generation<>policy.generation
        OR NEW.expires_at<=extract(epoch FROM clock_timestamp())
    THEN RAISE EXCEPTION 'Wire policy unavailable'; END IF;
    IF TG_OP='UPDATE' THEN
        IF ROW(NEW.tenant_id,NEW.reservation_id,NEW.generation,NEW.consumer,NEW.purpose,NEW.issued_at,NEW.expires_at,NEW.reserved_bytes)
            IS DISTINCT FROM ROW(OLD.tenant_id,OLD.reservation_id,OLD.generation,OLD.consumer,OLD.purpose,OLD.issued_at,OLD.expires_at,OLD.reserved_bytes)
            OR OLD.claimed OR NOT NEW.claimed
        THEN RAISE EXCEPTION 'Wire claim already consumed or changed'; END IF;
        RETURN NEW;
    END IF;
    IF NEW.claimed OR abs(NEW.issued_at-extract(epoch FROM clock_timestamp()))>2
    THEN RAISE EXCEPTION 'Wire reservation unavailable'; END IF;
    -- No partition by service, consumer, region or generation. Retain all charges.
    IF COALESCE((SELECT sum(reserved_bytes) FROM wire_reservations
        WHERE tenant_id=NEW.tenant_id AND issued_at/86400=NEW.issued_at/86400),0)
        + NEW.reserved_bytes > policy.daily_bytes
    THEN RAISE EXCEPTION 'Aggregate wire budget exhausted'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER wire_guard BEFORE INSERT OR UPDATE ON wire_reservations
FOR EACH ROW EXECUTE FUNCTION wire_reservation_guard();
ALTER TABLE wire_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE wire_policies FORCE ROW LEVEL SECURITY;
CREATE POLICY wire_policy_scope ON wire_policies
USING (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid)
WITH CHECK (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid);
ALTER TABLE wire_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE wire_reservations FORCE ROW LEVEL SECURITY;
CREATE POLICY wire_reservation_scope ON wire_reservations
USING (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid)
WITH CHECK (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid);
REVOKE ALL ON FUNCTION wire_reservation_guard() FROM PUBLIC;
