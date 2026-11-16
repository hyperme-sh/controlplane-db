-- Explicitly installed private streaming metadata. Never installed at startup.
CREATE TABLE stream_policies (
    tenant_id uuid PRIMARY KEY REFERENCES tenants(id),
    daily_bytes bigint NOT NULL CHECK (daily_bytes BETWEEN 1407600000 AND 1099511627776),
    generation uuid NOT NULL CHECK (generation <> '00000000-0000-0000-0000-000000000000'),
    enabled boolean NOT NULL DEFAULT false
);
CREATE TABLE stream_sessions (
    tenant_id uuid NOT NULL REFERENCES stream_policies(tenant_id),
    reservation_id uuid NOT NULL,
    generation uuid NOT NULL,
    room text NOT NULL CHECK (length(room) BETWEEN 1 AND 512),
    principal text NOT NULL CHECK (length(principal) BETWEEN 1 AND 256),
    action text NOT NULL CHECK (action IN ('publish','read')),
    source_ip inet NOT NULL,
    token_hash text NOT NULL CHECK (token_hash ~ '^[a-f0-9]{64}$'),
    path text NOT NULL CHECK (path ~ '^stream/[a-f0-9]{32}/[a-f0-9]{32}$'),
    issued_at bigint NOT NULL,
    expires_at bigint NOT NULL,
    reserved_bytes bigint NOT NULL,
    phase smallint NOT NULL DEFAULT 0 CHECK (phase IN (0,1,2)),
    media_session uuid,
    PRIMARY KEY (tenant_id,reservation_id),
    UNIQUE (tenant_id,token_hash),
    UNIQUE (tenant_id,media_session),
    CHECK (issued_at >= 0 AND expires_at>issued_at AND expires_at-issued_at<=3600),
    CHECK (issued_at/86400=(expires_at-1)/86400),
    CHECK (reserved_bytes=(expires_at-issued_at)*391000),
    CHECK ((phase=0 AND media_session IS NULL) OR phase=2 OR (phase=1 AND media_session IS NOT NULL))
);
CREATE INDEX stream_session_capacity ON stream_sessions(tenant_id,phase,room,action);
CREATE INDEX stream_session_daily ON stream_sessions(tenant_id,issued_at);
CREATE FUNCTION stream_session_transition() RETURNS trigger
LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
DECLARE policy record;
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'Stream reservations require read committed isolation';
    END IF;
    PERFORM id FROM tenants WHERE id=NEW.tenant_id FOR UPDATE;
    SELECT * INTO policy FROM stream_policies WHERE tenant_id=NEW.tenant_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Stream tenant unavailable'; END IF;
    IF TG_OP='UPDATE' THEN
        IF ROW(NEW.tenant_id,NEW.reservation_id,NEW.generation,NEW.room,NEW.principal,NEW.action,NEW.source_ip,NEW.token_hash,NEW.path,NEW.issued_at,NEW.expires_at,NEW.reserved_bytes)
            IS DISTINCT FROM ROW(OLD.tenant_id,OLD.reservation_id,OLD.generation,OLD.room,OLD.principal,OLD.action,OLD.source_ip,OLD.token_hash,OLD.path,OLD.issued_at,OLD.expires_at,OLD.reserved_bytes)
            OR NOT (NEW.phase=OLD.phase OR (OLD.phase=0 AND NEW.phase IN (1,2)) OR (OLD.phase=1 AND NEW.phase=2))
            OR (OLD.media_session IS NOT NULL AND NEW.media_session IS DISTINCT FROM OLD.media_session)
            OR (NEW.phase=OLD.phase AND NEW.media_session IS DISTINCT FROM OLD.media_session)
        THEN RAISE EXCEPTION 'Invalid stream transition'; END IF;
        IF NEW.phase=1 AND (NOT policy.enabled OR NEW.generation<>policy.generation OR NEW.expires_at<=extract(epoch FROM clock_timestamp()))
        THEN RAISE EXCEPTION 'Stream policy expired'; END IF;
        RETURN NEW;
    END IF;
    IF NOT policy.enabled OR NEW.generation<>policy.generation OR NEW.phase<>0 OR NEW.media_session IS NOT NULL
        OR abs(NEW.issued_at-extract(epoch FROM clock_timestamp()))>2
    THEN RAISE EXCEPTION 'Stream policy unavailable'; END IF;
    IF (SELECT count(*) FROM stream_sessions WHERE tenant_id=NEW.tenant_id AND phase<>2)>=22
        OR (SELECT count(*) FROM stream_sessions WHERE tenant_id=NEW.tenant_id AND phase<>2 AND source_ip=NEW.source_ip)>=11
    THEN RAISE EXCEPTION 'Stream session capacity'; END IF;
    IF NEW.action='publish' THEN
        IF EXISTS(SELECT 1 FROM stream_sessions WHERE tenant_id=NEW.tenant_id AND phase<>2 AND room=NEW.room AND action='publish')
            OR (SELECT count(*) FROM stream_sessions WHERE tenant_id=NEW.tenant_id AND phase<>2 AND action='publish')>=2
        THEN RAISE EXCEPTION 'Stream publisher capacity'; END IF;
    ELSE
        IF NOT EXISTS(SELECT 1 FROM stream_sessions WHERE tenant_id=NEW.tenant_id AND phase=1 AND room=NEW.room AND action='publish' AND path=NEW.path AND generation=NEW.generation AND expires_at>=NEW.expires_at)
            OR (SELECT count(*) FROM stream_sessions WHERE tenant_id=NEW.tenant_id AND phase<>2 AND room=NEW.room AND action='read')>=10
        THEN RAISE EXCEPTION 'Stream reader capacity'; END IF;
    END IF;
    IF COALESCE((SELECT sum(reserved_bytes) FROM stream_sessions WHERE tenant_id=NEW.tenant_id AND issued_at/86400=NEW.issued_at/86400),0)+NEW.reserved_bytes>policy.daily_bytes
    THEN RAISE EXCEPTION 'Stream daily capacity'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER stream_session_guard BEFORE INSERT OR UPDATE ON stream_sessions
FOR EACH ROW EXECUTE FUNCTION stream_session_transition();
ALTER TABLE stream_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE stream_policies FORCE ROW LEVEL SECURITY;
CREATE POLICY stream_policies_scope ON stream_policies
USING (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid)
WITH CHECK (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid);
ALTER TABLE stream_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE stream_sessions FORCE ROW LEVEL SECURITY;
CREATE POLICY stream_sessions_scope ON stream_sessions
USING (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid)
WITH CHECK (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid);
REVOKE ALL ON FUNCTION stream_session_transition() FROM PUBLIC;
