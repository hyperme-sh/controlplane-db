-- Metadata only; ciphertext remains in the configured private provider.
CREATE TABLE storage_media_objects (
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    object_id text NOT NULL CHECK (object_id ~ '^media_p_[a-f0-9]{128}_[a-f0-9]{32}$'),
    owner_principal text NOT NULL CHECK (owner_principal ~ '^[A-Za-z0-9_-]{43}\.[A-Za-z0-9_-]{43}$'),
    issuer_id uuid NOT NULL CHECK (issuer_id <> '00000000-0000-0000-0000-000000000000'),
    policy_digest text NOT NULL CHECK (policy_digest ~ '^[a-f0-9]{64}$'),
    ownership_digest text NOT NULL CHECK (ownership_digest ~ '^[a-f0-9]{64}$'),
    issued_at bigint NOT NULL CHECK (issued_at BETWEEN 0 AND 9007199254740991),
    expires_at bigint NOT NULL CHECK (expires_at BETWEEN 0 AND 9007199254740991),
    source_id uuid NOT NULL CHECK (source_id <> '00000000-0000-0000-0000-000000000000'),
    allocation_id uuid NOT NULL CHECK (allocation_id <> '00000000-0000-0000-0000-000000000000'),
    phase smallint NOT NULL DEFAULT 0 CHECK (phase IN (0,1,2)),
    deletion_command text CHECK (deletion_command ~ '^[a-f0-9]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (expires_at>issued_at AND expires_at-issued_at<=300),
    PRIMARY KEY (tenant_id,object_id),
    UNIQUE (tenant_id,allocation_id),
    UNIQUE (tenant_id,deletion_command),
    CHECK ((phase=0 AND deletion_command IS NULL) OR (phase IN (1,2) AND deletion_command IS NOT NULL))
);
CREATE TABLE storage_media_refs (
    tenant_id uuid NOT NULL,
    object_id text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('ciphertext','wrap')),
    digest text NOT NULL CHECK (digest ~ '^[a-f0-9]{64}$'),
    byte_length bigint NOT NULL,
    PRIMARY KEY (tenant_id,object_id,kind,digest),
    FOREIGN KEY (tenant_id,object_id) REFERENCES storage_media_objects(tenant_id,object_id),
    CHECK ((kind='ciphertext' AND byte_length BETWEEN 33 AND 67108864)
        OR (kind='wrap' AND byte_length BETWEEN 1 AND 65536))
);
CREATE UNIQUE INDEX storage_media_one_ciphertext ON storage_media_refs(tenant_id,object_id) WHERE kind='ciphertext';
CREATE INDEX storage_media_digest_refs ON storage_media_refs(tenant_id,kind,digest);
CREATE INDEX storage_media_owner_objects ON storage_media_objects(tenant_id,owner_principal,phase);
CREATE FUNCTION storage_media_object_transition() RETURNS trigger
LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
BEGIN
    IF TG_OP='INSERT' THEN
        IF NEW.phase<>0 OR NEW.deletion_command IS NOT NULL THEN RAISE EXCEPTION 'Media objects start active'; END IF;
        RETURN NEW;
    END IF;
    IF TG_OP='DELETE' THEN RAISE EXCEPTION 'Media retirement markers are permanent'; END IF;
    IF ROW(NEW.tenant_id,NEW.object_id,NEW.owner_principal,NEW.source_id,NEW.allocation_id,NEW.issuer_id,NEW.policy_digest,NEW.ownership_digest,NEW.issued_at,NEW.expires_at,NEW.created_at)
        IS DISTINCT FROM ROW(OLD.tenant_id,OLD.object_id,OLD.owner_principal,OLD.source_id,OLD.allocation_id,OLD.issuer_id,OLD.policy_digest,OLD.ownership_digest,OLD.issued_at,OLD.expires_at,OLD.created_at)
        OR NOT (NEW.phase=OLD.phase OR NEW.phase=OLD.phase+1)
        OR (OLD.deletion_command IS NOT NULL AND NEW.deletion_command IS DISTINCT FROM OLD.deletion_command)
    THEN RAISE EXCEPTION 'Invalid media object transition'; END IF;
    IF NEW.phase=2 AND EXISTS (SELECT 1 FROM storage_media_refs WHERE tenant_id=NEW.tenant_id AND object_id=NEW.object_id)
    THEN RAISE EXCEPTION 'Media references remain'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER storage_media_object_guard BEFORE INSERT OR UPDATE OR DELETE ON storage_media_objects
FOR EACH ROW EXECUTE FUNCTION storage_media_object_transition();
CREATE FUNCTION storage_media_ref_transition() RETURNS trigger
LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
DECLARE target record; held_phase smallint;
BEGIN
    IF TG_OP='UPDATE' THEN RAISE EXCEPTION 'Media references are immutable'; END IF;
    IF TG_OP='DELETE' THEN target:=OLD; ELSE target:=NEW; END IF;
    SELECT phase INTO held_phase FROM storage_media_objects
        WHERE tenant_id=target.tenant_id AND object_id=target.object_id FOR UPDATE;
    IF (TG_OP='INSERT' AND held_phase IS DISTINCT FROM 0) OR (TG_OP='DELETE' AND held_phase IS DISTINCT FROM 1)
    THEN RAISE EXCEPTION 'Media object phase refuses reference change'; END IF;
    IF TG_OP='DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER storage_media_ref_guard BEFORE INSERT OR UPDATE OR DELETE ON storage_media_refs
FOR EACH ROW EXECUTE FUNCTION storage_media_ref_transition();
ALTER TABLE storage_media_objects ENABLE ROW LEVEL SECURITY;
ALTER TABLE storage_media_objects FORCE ROW LEVEL SECURITY;
CREATE POLICY storage_media_objects_scope ON storage_media_objects
USING (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid)
WITH CHECK (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid);
ALTER TABLE storage_media_refs ENABLE ROW LEVEL SECURITY;
ALTER TABLE storage_media_refs FORCE ROW LEVEL SECURITY;
CREATE POLICY storage_media_refs_scope ON storage_media_refs
USING (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid)
WITH CHECK (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid);
REVOKE ALL ON FUNCTION storage_media_object_transition(),storage_media_ref_transition() FROM PUBLIC;
