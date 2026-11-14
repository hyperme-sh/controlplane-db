-- Provider location is metadata, never a credential or a caller-selected URL.
CREATE TABLE storage_media_locations (
    tenant_id uuid NOT NULL,
    object_id text NOT NULL,
    provider_location text NOT NULL CHECK (provider_location ~ '^[a-f0-9]{64}$'),
    PRIMARY KEY (tenant_id,object_id),
    FOREIGN KEY (tenant_id,object_id) REFERENCES storage_media_objects(tenant_id,object_id)
);
CREATE FUNCTION storage_media_location_transition() RETURNS trigger
LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
DECLARE held_phase smallint;
BEGIN
    IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Media provider bindings are permanent'; END IF;
    SELECT phase INTO held_phase FROM storage_media_objects
        WHERE tenant_id=NEW.tenant_id AND object_id=NEW.object_id FOR UPDATE;
    IF held_phase IS DISTINCT FROM 0 OR EXISTS (
        SELECT 1 FROM storage_media_refs WHERE tenant_id=NEW.tenant_id AND object_id=NEW.object_id)
    THEN RAISE EXCEPTION 'Existing media requires explicit provider reconciliation'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER storage_media_location_guard BEFORE INSERT OR UPDATE OR DELETE ON storage_media_locations
FOR EACH ROW EXECUTE FUNCTION storage_media_location_transition();
ALTER TABLE storage_media_locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE storage_media_locations FORCE ROW LEVEL SECURITY;
CREATE POLICY storage_media_locations_scope ON storage_media_locations
USING (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid)
WITH CHECK (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid);
REVOKE ALL ON FUNCTION storage_media_location_transition() FROM PUBLIC;
