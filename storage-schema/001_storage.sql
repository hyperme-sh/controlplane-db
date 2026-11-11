-- A private owner schema. The tenant registry contains declared IDs only;
-- current administration/key authority remains with user-service.
CREATE TABLE tenants (id uuid PRIMARY KEY);
CREATE TABLE storage_settings (
    id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    tenant_id uuid NOT NULL REFERENCES tenants(id),
    provider varchar(64) NOT NULL CHECK (provider IN ('s3', 'azure_blob')),
    is_enabled boolean NOT NULL,
    region varchar(128) NOT NULL,
    aws_access_key text,
    aws_secret_key text,
    aws_bucket_name varchar(512),
    azure_connection_string text,
    azure_container_name varchar(512),
    updated_by_user_id varchar(64)
);
CREATE UNIQUE INDEX uq_storage_tenant_provider ON storage_settings(tenant_id, provider);
CREATE UNIQUE INDEX uq_storage_tenant_active ON storage_settings(tenant_id) WHERE is_enabled;
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenants FORCE ROW LEVEL SECURITY;
CREATE POLICY storage_tenant_scope ON tenants
    USING (id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
    WITH CHECK (id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
ALTER TABLE storage_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE storage_settings FORCE ROW LEVEL SECURITY;
CREATE POLICY storage_setting_scope ON storage_settings
    USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
