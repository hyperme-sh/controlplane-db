-- Metadata only; ciphertext remains in the configured private provider.
CREATE TABLE storage_group_objects (
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    set_id text NOT NULL CHECK (set_id ~ '^set_p_[a-f0-9]{128}_[a-f0-9]{32}$'),
    predicate text NOT NULL CHECK (predicate IN ('same-group','named-circle')),
    owner_principal text NOT NULL CHECK (owner_principal ~ '^[A-Za-z0-9_-]{43}\.[A-Za-z0-9_-]{43}$'),
    issuer_id uuid NOT NULL CHECK (issuer_id <> '00000000-0000-0000-0000-000000000000'),
    policy_digest text NOT NULL CHECK (policy_digest ~ '^[a-f0-9]{64}$'),
    creation_digest text NOT NULL CHECK (creation_digest ~ '^[a-f0-9]{64}$'),
    issued_at bigint NOT NULL CHECK (issued_at BETWEEN 0 AND 9007199254740991),
    expires_at bigint NOT NULL CHECK (expires_at BETWEEN 0 AND 9007199254740991),
    source_id uuid NOT NULL CHECK (source_id <> '00000000-0000-0000-0000-000000000000'),
    allocation_id uuid NOT NULL CHECK (allocation_id <> '00000000-0000-0000-0000-000000000000'),
    phase smallint NOT NULL DEFAULT 0 CHECK (phase IN (0,1,2)),
    deletion_command text CHECK (deletion_command ~ '^[a-f0-9]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (expires_at>issued_at AND expires_at-issued_at<=300),
    PRIMARY KEY (tenant_id,set_id),
    UNIQUE (tenant_id,allocation_id),
    UNIQUE (tenant_id,deletion_command),
    CHECK ((phase=0 AND deletion_command IS NULL) OR (phase IN (1,2) AND deletion_command IS NOT NULL))
);
CREATE TABLE storage_group_refs (
    tenant_id uuid NOT NULL,
    set_id text NOT NULL,
    digest text NOT NULL CHECK (digest ~ '^[a-f0-9]{64}$'),
    byte_length bigint NOT NULL,
    PRIMARY KEY (tenant_id,set_id,digest),
    FOREIGN KEY (tenant_id,set_id) REFERENCES storage_group_objects(tenant_id,set_id),
    CHECK (byte_length BETWEEN 1 AND 65536)
);
CREATE INDEX storage_group_digest_refs ON storage_group_refs(tenant_id,digest);
CREATE INDEX storage_group_owner_objects ON storage_group_objects(tenant_id,owner_principal,phase);
CREATE FUNCTION storage_group_object_transition() RETURNS trigger
LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
BEGIN
    IF TG_OP='INSERT' THEN
        PERFORM id FROM tenants WHERE id=NEW.tenant_id FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'Group tenant unavailable'; END IF;
        IF (SELECT count(*) FROM storage_group_objects WHERE tenant_id=NEW.tenant_id AND phase<>2)>=64
        THEN RAISE EXCEPTION 'Group allocation capacity'; END IF;
        IF NEW.phase<>0 OR NEW.deletion_command IS NOT NULL THEN RAISE EXCEPTION 'Group objects start active'; END IF;
        RETURN NEW;
    END IF;
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Group retirement markers are permanent'; END IF;
    IF ROW(NEW.tenant_id,NEW.set_id,NEW.predicate,NEW.owner_principal,NEW.source_id,NEW.allocation_id,NEW.issuer_id,NEW.policy_digest,NEW.creation_digest,NEW.issued_at,NEW.expires_at,NEW.created_at)
        IS DISTINCT FROM ROW(OLD.tenant_id,OLD.set_id,OLD.predicate,OLD.owner_principal,OLD.source_id,OLD.allocation_id,OLD.issuer_id,OLD.policy_digest,OLD.creation_digest,OLD.issued_at,OLD.expires_at,OLD.created_at)
        OR NOT (NEW.phase=OLD.phase OR NEW.phase=OLD.phase+1)
        OR (OLD.deletion_command IS NOT NULL AND NEW.deletion_command IS DISTINCT FROM OLD.deletion_command)
    THEN RAISE EXCEPTION 'Invalid group object transition'; END IF;
    IF NEW.phase=2 AND EXISTS (SELECT 1 FROM storage_group_refs WHERE tenant_id=NEW.tenant_id AND set_id=NEW.set_id)
    THEN RAISE EXCEPTION 'Group references remain'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER storage_group_object_guard BEFORE INSERT OR UPDATE OR DELETE ON storage_group_objects
FOR EACH ROW EXECUTE FUNCTION storage_group_object_transition();
CREATE FUNCTION storage_group_ref_transition() RETURNS trigger
LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
DECLARE target record; held_phase smallint;
BEGIN
    IF TG_OP='UPDATE' THEN RAISE EXCEPTION 'Group references are immutable'; END IF;
    IF TG_OP='DELETE' THEN target:=OLD; ELSE target:=NEW; END IF;
    SELECT phase INTO held_phase FROM storage_group_objects
        WHERE tenant_id=target.tenant_id AND set_id=target.set_id FOR UPDATE;
    IF (TG_OP='INSERT' AND held_phase IS DISTINCT FROM 0) OR (TG_OP='DELETE' AND held_phase IS DISTINCT FROM 1)
    THEN RAISE EXCEPTION 'Group object phase refuses reference change'; END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    IF (SELECT count(*) FROM storage_group_refs WHERE tenant_id=NEW.tenant_id AND set_id=NEW.set_id)>=4096
    THEN RAISE EXCEPTION 'Group wrap capacity'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER storage_group_ref_guard BEFORE INSERT OR UPDATE OR DELETE ON storage_group_refs
FOR EACH ROW EXECUTE FUNCTION storage_group_ref_transition();
ALTER TABLE storage_group_objects ENABLE ROW LEVEL SECURITY;
ALTER TABLE storage_group_objects FORCE ROW LEVEL SECURITY;
CREATE POLICY storage_group_objects_scope ON storage_group_objects
USING (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid)
WITH CHECK (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid);
ALTER TABLE storage_group_refs ENABLE ROW LEVEL SECURITY;
ALTER TABLE storage_group_refs FORCE ROW LEVEL SECURITY;
CREATE POLICY storage_group_refs_scope ON storage_group_refs
USING (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid)
WITH CHECK (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid);
REVOKE ALL ON FUNCTION storage_group_object_transition(),storage_group_ref_transition() FROM PUBLIC;
