-- Provider location is metadata, never a credential or a caller-selected URL.
CREATE TABLE storage_group_locations (
    tenant_id uuid NOT NULL,
    set_id text NOT NULL,
    provider_location text NOT NULL CHECK (provider_location ~ '^[a-f0-9]{64}$'),
    PRIMARY KEY (tenant_id,set_id),
    FOREIGN KEY (tenant_id,set_id) REFERENCES storage_group_objects(tenant_id,set_id)
);
CREATE FUNCTION storage_group_location_transition() RETURNS trigger
LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
DECLARE held_phase smallint;
BEGIN
    IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'Group storage requires read committed isolation';
    END IF;
    IF TG_OP<>'INSERT' THEN RAISE EXCEPTION 'Group provider bindings are permanent'; END IF;
    SELECT phase INTO held_phase FROM storage_group_objects
        WHERE tenant_id=NEW.tenant_id AND set_id=NEW.set_id FOR UPDATE;
    IF held_phase IS DISTINCT FROM 0 OR EXISTS (
        SELECT 1 FROM storage_group_refs WHERE tenant_id=NEW.tenant_id AND set_id=NEW.set_id)
    THEN RAISE EXCEPTION 'Existing group requires explicit provider reconciliation'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER storage_group_location_guard BEFORE INSERT OR UPDATE OR DELETE ON storage_group_locations
FOR EACH ROW EXECUTE FUNCTION storage_group_location_transition();
ALTER TABLE storage_group_locations ENABLE ROW LEVEL SECURITY;
ALTER TABLE storage_group_locations FORCE ROW LEVEL SECURITY;
CREATE POLICY storage_group_locations_scope ON storage_group_locations
USING (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid)
WITH CHECK (tenant_id=NULLIF(current_setting('app.current_tenant_id',true),'')::uuid);
REVOKE ALL ON FUNCTION storage_group_location_transition() FROM PUBLIC;
