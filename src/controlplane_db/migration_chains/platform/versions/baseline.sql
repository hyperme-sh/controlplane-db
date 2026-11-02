-- Frozen schema-only baseline at 0053_onboarding_runs. No seed data.
SET LOCAL search_path = public, pg_catalog;
SET LOCAL check_function_bodies = false;

-- TABLE: sociacl_share_links
CREATE TABLE public.sociacl_share_links (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    token_hash character varying(64) NOT NULL,
    token_prefix character varying(16) NOT NULL,
    owner_user_id uuid,
    group_id uuid,
    resource_kind character varying(32) NOT NULL,
    resource_descriptor jsonb DEFAULT '{}'::jsonb NOT NULL,
    predicate_json jsonb DEFAULT '{}'::jsonb NOT NULL,
    mode character varying(32) NOT NULL,
    expires_at timestamp with time zone,
    uses_remaining integer,
    revoked_at timestamp with time zone,
    created_by character varying(512),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.sociacl_share_links FORCE ROW LEVEL SECURITY;


--

-- FUNCTION: sociacl_share_lookup_by_hash(character varying)
CREATE FUNCTION public.sociacl_share_lookup_by_hash(p_hash character varying) RETURNS SETOF public.sociacl_share_links
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
              SELECT * FROM sociacl_share_links WHERE token_hash = p_hash LIMIT 1;
            $$;


--

-- TABLE: acl_casbin_rules
CREATE TABLE public.acl_casbin_rules (
    id integer NOT NULL,
    tenant_id uuid NOT NULL,
    ptype character varying(255),
    v0 character varying(255),
    v1 character varying(255),
    v2 character varying(255),
    v3 character varying(255),
    v4 character varying(255),
    v5 character varying(255),
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.acl_casbin_rules FORCE ROW LEVEL SECURITY;


--

-- SEQUENCE: acl_casbin_rules_id_seq
CREATE SEQUENCE public.acl_casbin_rules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--

-- SEQUENCE OWNED BY: acl_casbin_rules_id_seq
ALTER SEQUENCE public.acl_casbin_rules_id_seq OWNED BY public.acl_casbin_rules.id;


--

-- TABLE: ai_agent_entitlements
CREATE TABLE public.ai_agent_entitlements (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL,
    buyer_id uuid NOT NULL,
    purchase_id uuid NOT NULL,
    listing_id uuid NOT NULL,
    license_key_sha256 character varying(64) NOT NULL
);

ALTER TABLE ONLY public.ai_agent_entitlements FORCE ROW LEVEL SECURITY;


--

-- TABLE: ai_budget_event_audit
CREATE TABLE public.ai_budget_event_audit (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL,
    budget_id uuid NOT NULL,
    user_id uuid,
    delta_lamports bigint NOT NULL,
    allocated_after bigint NOT NULL,
    ceiling_lamports bigint NOT NULL,
    source_event_id bigint,
    source_event_key character varying(128)
);

ALTER TABLE ONLY public.ai_budget_event_audit FORCE ROW LEVEL SECURITY;


--

-- TABLE: ai_inference_records
CREATE TABLE public.ai_inference_records (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    model character varying(256) NOT NULL,
    input_tokens integer NOT NULL,
    output_tokens integer NOT NULL,
    cost_usd numeric(24,12) NOT NULL,
    billing_mode character varying(32) NOT NULL,
    budget_id uuid
);

ALTER TABLE ONLY public.ai_inference_records FORCE ROW LEVEL SECURITY;


--

-- TABLE: api_keys
CREATE TABLE public.api_keys (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL,
    key_prefix character varying(32) NOT NULL,
    secret_hash character varying(128) NOT NULL,
    name character varying(256),
    scopes jsonb,
    created_by_sub character varying(512),
    revoked_at timestamp with time zone,
    purpose character varying(32) NOT NULL,
    last_used_at timestamp with time zone,
    key_fingerprint character varying(64)
);


--

-- TABLE: billing_records
CREATE TABLE public.billing_records (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid,
    scope character varying(32) NOT NULL,
    actor character varying(32) NOT NULL,
    user_id uuid,
    payment_type character varying(64) NOT NULL,
    currency character varying(8) NOT NULL,
    amount integer,
    stripe_customer_id character varying(255),
    stripe_subscription_id character varying(255),
    stripe_session_id character varying(255),
    product_id character varying(255),
    price_id character varying(255),
    status character varying(64) NOT NULL,
    current_period_end timestamp with time zone,
    canceled_at timestamp with time zone,
    cancellation_reason text,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL
);

ALTER TABLE ONLY public.billing_records FORCE ROW LEVEL SECURITY;


--

-- TABLE: branding_configuration
CREATE TABLE public.branding_configuration (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid,
    logo_url text,
    logo_type character varying(64),
    favicon_url text,
    app_name character varying(255) NOT NULL,
    contact_info jsonb,
    theme_config jsonb DEFAULT '{}'::jsonb NOT NULL
);

ALTER TABLE ONLY public.branding_configuration FORCE ROW LEVEL SECURITY;


--

-- TABLE: chat_histories_ai
CREATE TABLE public.chat_histories_ai (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid,
    histories jsonb DEFAULT '[]'::jsonb NOT NULL
);

ALTER TABLE ONLY public.chat_histories_ai FORCE ROW LEVEL SECURITY;


--

-- TABLE: chat_sessions_ai
CREATE TABLE public.chat_sessions_ai (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid,
    session_id uuid NOT NULL,
    user_id uuid NOT NULL,
    history_id uuid NOT NULL
);

ALTER TABLE ONLY public.chat_sessions_ai FORCE ROW LEVEL SECURITY;


--

-- TABLE: crypto_agent_budgets
CREATE TABLE public.crypto_agent_budgets (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid,
    label character varying(255),
    owner_pubkey text NOT NULL,
    mint_pubkey text NOT NULL,
    ceiling_lamports bigint NOT NULL,
    allocated_lamports bigint NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.crypto_agent_budgets FORCE ROW LEVEL SECURITY;


--

-- TABLE: groups
CREATE TABLE public.groups (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL,
    name character varying(255) NOT NULL,
    description text,
    role_id uuid NOT NULL
);

ALTER TABLE ONLY public.groups FORCE ROW LEVEL SECURITY;


--

-- TABLE: marketplace_listings
CREATE TABLE public.marketplace_listings (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL,
    seller_id uuid NOT NULL,
    title character varying(512) NOT NULL,
    description text NOT NULL,
    listing_type character varying(32) NOT NULL,
    price_type character varying(32) NOT NULL,
    price_amount integer,
    metadata jsonb DEFAULT '{}'::jsonb NOT NULL,
    is_public boolean NOT NULL
);

ALTER TABLE ONLY public.marketplace_listings FORCE ROW LEVEL SECURITY;


--

-- TABLE: marketplace_purchases
CREATE TABLE public.marketplace_purchases (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL,
    listing_id uuid NOT NULL,
    buyer_id uuid NOT NULL,
    status character varying(32) NOT NULL,
    license_key character varying(512),
    billing_record_id uuid
);

ALTER TABLE ONLY public.marketplace_purchases FORCE ROW LEVEL SECURITY;


--

-- TABLE: marketplace_seller_profiles
CREATE TABLE public.marketplace_seller_profiles (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    status character varying(32) NOT NULL,
    verified_at timestamp with time zone
);

ALTER TABLE ONLY public.marketplace_seller_profiles FORCE ROW LEVEL SECURITY;


--

-- TABLE: notification_banner_settings
CREATE TABLE public.notification_banner_settings (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid,
    is_enabled boolean NOT NULL,
    message text
);

ALTER TABLE ONLY public.notification_banner_settings FORCE ROW LEVEL SECURITY;


--

-- TABLE: operator_audit
CREATE TABLE public.operator_audit (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    actor character varying(512) NOT NULL,
    action character varying(64) NOT NULL,
    target_kind character varying(32) NOT NULL,
    target_id character varying(64) NOT NULL,
    reason text NOT NULL,
    detail jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp with time zone NOT NULL
);

ALTER TABLE ONLY public.operator_audit FORCE ROW LEVEL SECURITY;


--

-- TABLE: operator_bans
CREATE TABLE public.operator_bans (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    subject_kind character varying(16) NOT NULL,
    subject_id uuid NOT NULL,
    reason text NOT NULL,
    created_by character varying(512) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    lifted_at timestamp with time zone,
    lifted_by character varying(512),
    lift_reason text,
    subject_label character varying(512)
);

ALTER TABLE ONLY public.operator_bans FORCE ROW LEVEL SECURITY;


--

-- TABLE: operator_mail_quota
CREATE TABLE public.operator_mail_quota (
    year_month character varying(7) NOT NULL,
    sent_count integer NOT NULL
);


--

-- TABLE: operator_peers
CREATE TABLE public.operator_peers (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    display_name character varying(256) NOT NULL,
    base_url character varying(512) NOT NULL,
    peer_tenant_id character varying(64) NOT NULL,
    last_health_ok boolean NOT NULL,
    last_health_detail character varying(500) NOT NULL,
    checked_at timestamp with time zone NOT NULL
);

ALTER TABLE ONLY public.operator_peers FORCE ROW LEVEL SECURITY;


--

-- TABLE: organization_idp_links
CREATE TABLE public.organization_idp_links (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL,
    organization_id uuid NOT NULL,
    provider character varying(32) NOT NULL,
    external_key character varying(256) NOT NULL,
    linked_by_sub character varying(512) NOT NULL
);

ALTER TABLE ONLY public.organization_idp_links FORCE ROW LEVEL SECURITY;


--

-- TABLE: organizations
CREATE TABLE public.organizations (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL,
    legal_name character varying(512) NOT NULL
);

ALTER TABLE ONLY public.organizations FORCE ROW LEVEL SECURITY;


--

-- TABLE: roles
CREATE TABLE public.roles (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid,
    name character varying(255) NOT NULL,
    description text,
    permissions jsonb DEFAULT '[]'::jsonb NOT NULL
);

ALTER TABLE ONLY public.roles FORCE ROW LEVEL SECURITY;


--

-- TABLE: sociacl_recovery_sessions
CREATE TABLE public.sociacl_recovery_sessions (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    state character varying(32) NOT NULL,
    idempotency_key character varying(128) NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    metadata jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.sociacl_recovery_sessions FORCE ROW LEVEL SECURITY;


--

-- TABLE: sso_settings
CREATE TABLE public.sso_settings (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid,
    enabled boolean NOT NULL,
    provider character varying(64),
    client_id text,
    client_secret text,
    scopes jsonb,
    redirect_uris jsonb
);

ALTER TABLE ONLY public.sso_settings FORCE ROW LEVEL SECURITY;


--

-- TABLE: storage_settings
CREATE TABLE public.storage_settings (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid,
    provider character varying(64) NOT NULL,
    is_enabled boolean NOT NULL,
    region character varying(128) NOT NULL,
    aws_access_key text,
    aws_secret_key text,
    aws_bucket_name character varying(512),
    azure_connection_string text,
    azure_container_name character varying(512),
    updated_by_user_id character varying(64)
);

ALTER TABLE ONLY public.storage_settings FORCE ROW LEVEL SECURITY;


--

-- TABLE: stripe_settings
CREATE TABLE public.stripe_settings (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid,
    default_currency character varying(8) NOT NULL,
    stripe_webhook_secret text NOT NULL,
    mode character varying(32) NOT NULL,
    trial_period_days integer NOT NULL,
    stripe_secret_key text
);

ALTER TABLE ONLY public.stripe_settings FORCE ROW LEVEL SECURITY;


--

-- TABLE: subscription_plans
CREATE TABLE public.subscription_plans (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid,
    plan_level jsonb NOT NULL,
    is_trial boolean NOT NULL,
    actor character varying(32) NOT NULL,
    user_id uuid,
    plan_id character varying(255) NOT NULL
);

ALTER TABLE ONLY public.subscription_plans FORCE ROW LEVEL SECURITY;


--

-- TABLE: tenants
CREATE TABLE public.tenants (
    id uuid NOT NULL,
    name character varying(512) NOT NULL,
    subdomain character varying(512),
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    is_active boolean NOT NULL,
    custom_domain character varying(512),
    custom_domain_status character varying(64) DEFAULT 'failed'::character varying NOT NULL,
    features jsonb,
    subscription_id uuid
);


--

-- TABLE: user_group_memberships
CREATE TABLE public.user_group_memberships (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid NOT NULL,
    user_id uuid NOT NULL,
    group_id uuid NOT NULL
);

ALTER TABLE ONLY public.user_group_memberships FORCE ROW LEVEL SECURITY;


--

-- TABLE: user_magic_links
CREATE TABLE public.user_magic_links (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid,
    user_id uuid NOT NULL,
    token text NOT NULL,
    expires_at timestamp with time zone NOT NULL
);

ALTER TABLE ONLY public.user_magic_links FORCE ROW LEVEL SECURITY;


--

-- TABLE: user_passkey_challenges
CREATE TABLE public.user_passkey_challenges (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid,
    email character varying(512) NOT NULL,
    type character varying(32) NOT NULL,
    challenge text NOT NULL,
    expires_at timestamp with time zone NOT NULL
);

ALTER TABLE ONLY public.user_passkey_challenges FORCE ROW LEVEL SECURITY;


--

-- TABLE: user_passkeys
CREATE TABLE public.user_passkeys (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid,
    user_email character varying(512) NOT NULL,
    credentials jsonb DEFAULT '[]'::jsonb NOT NULL
);

ALTER TABLE ONLY public.user_passkeys FORCE ROW LEVEL SECURITY;


--

-- TABLE: user_password_resets
CREATE TABLE public.user_password_resets (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid,
    user_id uuid NOT NULL,
    token_secret text NOT NULL,
    reset_secret_updated_at timestamp with time zone NOT NULL,
    first_name character varying(255) NOT NULL
);

ALTER TABLE ONLY public.user_password_resets FORCE ROW LEVEL SECURITY;


--

-- TABLE: user_preferences
CREATE TABLE public.user_preferences (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid,
    user_id uuid NOT NULL,
    preferences jsonb DEFAULT '{}'::jsonb NOT NULL
);

ALTER TABLE ONLY public.user_preferences FORCE ROW LEVEL SECURITY;


--

-- TABLE: user_wallet_bindings
CREATE TABLE public.user_wallet_bindings (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    keycloak_sub character varying(512) NOT NULL,
    email character varying(512),
    wallet_address character varying(42) NOT NULL,
    bound_at timestamp with time zone DEFAULT now() NOT NULL
);


--

-- TABLE: users
CREATE TABLE public.users (
    id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    tenant_id uuid,
    first_name character varying(255) NOT NULL,
    last_name character varying(255) NOT NULL,
    email character varying(512) NOT NULL,
    gender character varying(64) NOT NULL,
    role_id uuid,
    is_active boolean NOT NULL,
    activated_at timestamp with time zone,
    image_url text,
    password text,
    sso_provider_id character varying(512),
    keycloak_sub character varying(512),
    deleted_at timestamp with time zone,
    sociacl_attributes jsonb
);

ALTER TABLE ONLY public.users FORCE ROW LEVEL SECURITY;


--

-- DEFAULT: acl_casbin_rules id
ALTER TABLE ONLY public.acl_casbin_rules ALTER COLUMN id SET DEFAULT nextval('public.acl_casbin_rules_id_seq'::regclass);


--

-- CONSTRAINT: acl_casbin_rules acl_casbin_rules_pkey
ALTER TABLE ONLY public.acl_casbin_rules
    ADD CONSTRAINT acl_casbin_rules_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: ai_agent_entitlements ai_agent_entitlements_pkey
ALTER TABLE ONLY public.ai_agent_entitlements
    ADD CONSTRAINT ai_agent_entitlements_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: ai_budget_event_audit ai_budget_event_audit_pkey
ALTER TABLE ONLY public.ai_budget_event_audit
    ADD CONSTRAINT ai_budget_event_audit_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: ai_inference_records ai_inference_records_pkey
ALTER TABLE ONLY public.ai_inference_records
    ADD CONSTRAINT ai_inference_records_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: api_keys api_keys_pkey
ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: billing_records billing_records_pkey
ALTER TABLE ONLY public.billing_records
    ADD CONSTRAINT billing_records_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: branding_configuration branding_configuration_pkey
ALTER TABLE ONLY public.branding_configuration
    ADD CONSTRAINT branding_configuration_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: chat_histories_ai chat_histories_ai_pkey
ALTER TABLE ONLY public.chat_histories_ai
    ADD CONSTRAINT chat_histories_ai_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: chat_sessions_ai chat_sessions_ai_pkey
ALTER TABLE ONLY public.chat_sessions_ai
    ADD CONSTRAINT chat_sessions_ai_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: crypto_agent_budgets crypto_agent_budgets_pkey
ALTER TABLE ONLY public.crypto_agent_budgets
    ADD CONSTRAINT crypto_agent_budgets_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: groups groups_pkey
ALTER TABLE ONLY public.groups
    ADD CONSTRAINT groups_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: marketplace_listings marketplace_listings_pkey
ALTER TABLE ONLY public.marketplace_listings
    ADD CONSTRAINT marketplace_listings_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: marketplace_purchases marketplace_purchases_pkey
ALTER TABLE ONLY public.marketplace_purchases
    ADD CONSTRAINT marketplace_purchases_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: marketplace_seller_profiles marketplace_seller_profiles_pkey
ALTER TABLE ONLY public.marketplace_seller_profiles
    ADD CONSTRAINT marketplace_seller_profiles_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: notification_banner_settings notification_banner_settings_pkey
ALTER TABLE ONLY public.notification_banner_settings
    ADD CONSTRAINT notification_banner_settings_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: operator_audit operator_audit_pkey
ALTER TABLE ONLY public.operator_audit
    ADD CONSTRAINT operator_audit_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: operator_bans operator_bans_pkey
ALTER TABLE ONLY public.operator_bans
    ADD CONSTRAINT operator_bans_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: operator_mail_quota operator_mail_quota_pkey
ALTER TABLE ONLY public.operator_mail_quota
    ADD CONSTRAINT operator_mail_quota_pkey PRIMARY KEY (year_month);


--

-- CONSTRAINT: operator_peers operator_peers_pkey
ALTER TABLE ONLY public.operator_peers
    ADD CONSTRAINT operator_peers_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: organization_idp_links organization_idp_links_pkey
ALTER TABLE ONLY public.organization_idp_links
    ADD CONSTRAINT organization_idp_links_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: organizations organizations_pkey
ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: roles roles_pkey
ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: sociacl_recovery_sessions sociacl_recovery_sessions_pkey
ALTER TABLE ONLY public.sociacl_recovery_sessions
    ADD CONSTRAINT sociacl_recovery_sessions_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: sociacl_share_links sociacl_share_links_pkey
ALTER TABLE ONLY public.sociacl_share_links
    ADD CONSTRAINT sociacl_share_links_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: sociacl_share_links sociacl_share_links_token_hash_key
ALTER TABLE ONLY public.sociacl_share_links
    ADD CONSTRAINT sociacl_share_links_token_hash_key UNIQUE (token_hash);


--

-- CONSTRAINT: sso_settings sso_settings_pkey
ALTER TABLE ONLY public.sso_settings
    ADD CONSTRAINT sso_settings_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: storage_settings storage_settings_pkey
ALTER TABLE ONLY public.storage_settings
    ADD CONSTRAINT storage_settings_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: stripe_settings stripe_settings_pkey
ALTER TABLE ONLY public.stripe_settings
    ADD CONSTRAINT stripe_settings_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: subscription_plans subscription_plans_pkey
ALTER TABLE ONLY public.subscription_plans
    ADD CONSTRAINT subscription_plans_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: tenants tenants_custom_domain_key
ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_custom_domain_key UNIQUE (custom_domain);


--

-- CONSTRAINT: tenants tenants_name_key
ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_name_key UNIQUE (name);


--

-- CONSTRAINT: tenants tenants_pkey
ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: tenants tenants_subdomain_key
ALTER TABLE ONLY public.tenants
    ADD CONSTRAINT tenants_subdomain_key UNIQUE (subdomain);


--

-- CONSTRAINT: ai_agent_entitlements uq_ai_agent_ent_tenant_purchase
ALTER TABLE ONLY public.ai_agent_entitlements
    ADD CONSTRAINT uq_ai_agent_ent_tenant_purchase UNIQUE (tenant_id, purchase_id);


--

-- CONSTRAINT: api_keys uq_api_keys_prefix
ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT uq_api_keys_prefix UNIQUE (key_prefix);


--

-- CONSTRAINT: marketplace_seller_profiles uq_mkt_seller_tenant_user
ALTER TABLE ONLY public.marketplace_seller_profiles
    ADD CONSTRAINT uq_mkt_seller_tenant_user UNIQUE (tenant_id, user_id);


--

-- CONSTRAINT: organization_idp_links uq_org_idp_provider_key
ALTER TABLE ONLY public.organization_idp_links
    ADD CONSTRAINT uq_org_idp_provider_key UNIQUE (tenant_id, provider, external_key);


--

-- CONSTRAINT: organizations uq_organizations_id_tenant
ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT uq_organizations_id_tenant UNIQUE (id, tenant_id);


--

-- CONSTRAINT: user_group_memberships user_group_memberships_pkey
ALTER TABLE ONLY public.user_group_memberships
    ADD CONSTRAINT user_group_memberships_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: user_magic_links user_magic_links_pkey
ALTER TABLE ONLY public.user_magic_links
    ADD CONSTRAINT user_magic_links_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: user_passkey_challenges user_passkey_challenges_pkey
ALTER TABLE ONLY public.user_passkey_challenges
    ADD CONSTRAINT user_passkey_challenges_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: user_passkeys user_passkeys_pkey
ALTER TABLE ONLY public.user_passkeys
    ADD CONSTRAINT user_passkeys_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: user_password_resets user_password_resets_pkey
ALTER TABLE ONLY public.user_password_resets
    ADD CONSTRAINT user_password_resets_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: user_preferences user_preferences_pkey
ALTER TABLE ONLY public.user_preferences
    ADD CONSTRAINT user_preferences_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: user_wallet_bindings user_wallet_bindings_pkey
ALTER TABLE ONLY public.user_wallet_bindings
    ADD CONSTRAINT user_wallet_bindings_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: users users_pkey
ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--

-- INDEX: ix_acl_casbin_rules_tenant
CREATE INDEX ix_acl_casbin_rules_tenant ON public.acl_casbin_rules USING btree (tenant_id);


--

-- INDEX: ix_ai_agent_ent_buyer
CREATE INDEX ix_ai_agent_ent_buyer ON public.ai_agent_entitlements USING btree (tenant_id, buyer_id);


--

-- INDEX: ix_ai_budget_audit_tenant
CREATE INDEX ix_ai_budget_audit_tenant ON public.ai_budget_event_audit USING btree (tenant_id);


--

-- INDEX: ix_ai_inference_tenant
CREATE INDEX ix_ai_inference_tenant ON public.ai_inference_records USING btree (tenant_id);


--

-- INDEX: ix_ai_inference_user
CREATE INDEX ix_ai_inference_user ON public.ai_inference_records USING btree (tenant_id, user_id);


--

-- INDEX: ix_api_keys_tenant
CREATE INDEX ix_api_keys_tenant ON public.api_keys USING btree (tenant_id);


--

-- INDEX: ix_billing_session
CREATE INDEX ix_billing_session ON public.billing_records USING btree (stripe_session_id);


--

-- INDEX: ix_billing_tenant_sub
CREATE INDEX ix_billing_tenant_sub ON public.billing_records USING btree (tenant_id, stripe_subscription_id);


--

-- INDEX: ix_crypto_agent_budgets_tenant
CREATE INDEX ix_crypto_agent_budgets_tenant ON public.crypto_agent_budgets USING btree (tenant_id);


--

-- INDEX: ix_marketplace_listings_tenant
CREATE INDEX ix_marketplace_listings_tenant ON public.marketplace_listings USING btree (tenant_id);


--

-- INDEX: ix_mkt_seller_profiles_tenant
CREATE INDEX ix_mkt_seller_profiles_tenant ON public.marketplace_seller_profiles USING btree (tenant_id);


--

-- INDEX: ix_operator_audit_tenant
CREATE INDEX ix_operator_audit_tenant ON public.operator_audit USING btree (tenant_id);


--

-- INDEX: ix_operator_bans_tenant
CREATE INDEX ix_operator_bans_tenant ON public.operator_bans USING btree (tenant_id);


--

-- INDEX: ix_operator_peers_tenant
CREATE INDEX ix_operator_peers_tenant ON public.operator_peers USING btree (tenant_id);


--

-- INDEX: ix_org_idp_links_org
CREATE INDEX ix_org_idp_links_org ON public.organization_idp_links USING btree (organization_id);


--

-- INDEX: ix_sociacl_recovery_sessions_tenant
CREATE INDEX ix_sociacl_recovery_sessions_tenant ON public.sociacl_recovery_sessions USING btree (tenant_id);


--

-- INDEX: ix_sociacl_share_links_tenant
CREATE INDEX ix_sociacl_share_links_tenant ON public.sociacl_share_links USING btree (tenant_id);


--

-- INDEX: ix_users_keycloak_sub_unique
CREATE UNIQUE INDEX ix_users_keycloak_sub_unique ON public.users USING btree (keycloak_sub) WHERE (keycloak_sub IS NOT NULL);


--

-- INDEX: uq_acl_casbin_rules_identity
CREATE UNIQUE INDEX uq_acl_casbin_rules_identity ON public.acl_casbin_rules USING btree (tenant_id, ptype, v0, v1, v2, v3, v4, v5) NULLS NOT DISTINCT;


--

-- INDEX: uq_ai_budget_event_audit_source_event
CREATE UNIQUE INDEX uq_ai_budget_event_audit_source_event ON public.ai_budget_event_audit USING btree (source_event_id);


--

-- INDEX: uq_ai_budget_event_audit_source_key
CREATE UNIQUE INDEX uq_ai_budget_event_audit_source_key ON public.ai_budget_event_audit USING btree (source_event_key);


--

-- INDEX: uq_groups_tenant_name
CREATE UNIQUE INDEX uq_groups_tenant_name ON public.groups USING btree (tenant_id, name);


--

-- INDEX: uq_operator_bans_active
CREATE UNIQUE INDEX uq_operator_bans_active ON public.operator_bans USING btree (tenant_id, subject_kind, subject_id) WHERE (lifted_at IS NULL);


--

-- INDEX: uq_organizations_tenant_legal_name
CREATE UNIQUE INDEX uq_organizations_tenant_legal_name ON public.organizations USING btree (tenant_id, legal_name);


--

-- INDEX: uq_roles_platform_lower_name
CREATE UNIQUE INDEX uq_roles_platform_lower_name ON public.roles USING btree (lower((name)::text)) WHERE (tenant_id IS NULL);


--

-- INDEX: uq_roles_platform_name
CREATE UNIQUE INDEX uq_roles_platform_name ON public.roles USING btree (name) WHERE (tenant_id IS NULL);


--

-- INDEX: uq_roles_tenant_lower_name
CREATE UNIQUE INDEX uq_roles_tenant_lower_name ON public.roles USING btree (tenant_id, lower((name)::text)) WHERE (tenant_id IS NOT NULL);


--

-- INDEX: uq_roles_tenant_name
CREATE UNIQUE INDEX uq_roles_tenant_name ON public.roles USING btree (tenant_id, name) WHERE (tenant_id IS NOT NULL);


--

-- INDEX: uq_sociacl_share_links_token_hash
CREATE UNIQUE INDEX uq_sociacl_share_links_token_hash ON public.sociacl_share_links USING btree (token_hash);


--

-- INDEX: uq_storage_tenant_provider
CREATE UNIQUE INDEX uq_storage_tenant_provider ON public.storage_settings USING btree (tenant_id, provider) WHERE (tenant_id IS NOT NULL);


--

-- INDEX: uq_user_group_memberships_user_group
CREATE UNIQUE INDEX uq_user_group_memberships_user_group ON public.user_group_memberships USING btree (user_id, group_id);


--

-- INDEX: uq_user_wallet_bindings_address
CREATE UNIQUE INDEX uq_user_wallet_bindings_address ON public.user_wallet_bindings USING btree (wallet_address);


--

-- INDEX: uq_user_wallet_bindings_sub
CREATE UNIQUE INDEX uq_user_wallet_bindings_sub ON public.user_wallet_bindings USING btree (keycloak_sub);


--

-- INDEX: uq_users_platform_email
CREATE UNIQUE INDEX uq_users_platform_email ON public.users USING btree (email) WHERE (tenant_id IS NULL);


--

-- INDEX: uq_users_tenant_email
CREATE UNIQUE INDEX uq_users_tenant_email ON public.users USING btree (tenant_id, email) WHERE (tenant_id IS NOT NULL);


--

-- FK CONSTRAINT: acl_casbin_rules acl_casbin_rules_tenant_id_fkey
ALTER TABLE ONLY public.acl_casbin_rules
    ADD CONSTRAINT acl_casbin_rules_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: ai_agent_entitlements ai_agent_entitlements_buyer_id_fkey
ALTER TABLE ONLY public.ai_agent_entitlements
    ADD CONSTRAINT ai_agent_entitlements_buyer_id_fkey FOREIGN KEY (buyer_id) REFERENCES public.users(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: ai_agent_entitlements ai_agent_entitlements_listing_id_fkey
ALTER TABLE ONLY public.ai_agent_entitlements
    ADD CONSTRAINT ai_agent_entitlements_listing_id_fkey FOREIGN KEY (listing_id) REFERENCES public.marketplace_listings(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: ai_agent_entitlements ai_agent_entitlements_purchase_id_fkey
ALTER TABLE ONLY public.ai_agent_entitlements
    ADD CONSTRAINT ai_agent_entitlements_purchase_id_fkey FOREIGN KEY (purchase_id) REFERENCES public.marketplace_purchases(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: ai_agent_entitlements ai_agent_entitlements_tenant_id_fkey
ALTER TABLE ONLY public.ai_agent_entitlements
    ADD CONSTRAINT ai_agent_entitlements_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: ai_budget_event_audit ai_budget_event_audit_budget_id_fkey
ALTER TABLE ONLY public.ai_budget_event_audit
    ADD CONSTRAINT ai_budget_event_audit_budget_id_fkey FOREIGN KEY (budget_id) REFERENCES public.crypto_agent_budgets(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: ai_budget_event_audit ai_budget_event_audit_tenant_id_fkey
ALTER TABLE ONLY public.ai_budget_event_audit
    ADD CONSTRAINT ai_budget_event_audit_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: ai_budget_event_audit ai_budget_event_audit_user_id_fkey
ALTER TABLE ONLY public.ai_budget_event_audit
    ADD CONSTRAINT ai_budget_event_audit_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--

-- FK CONSTRAINT: ai_inference_records ai_inference_records_budget_id_fkey
ALTER TABLE ONLY public.ai_inference_records
    ADD CONSTRAINT ai_inference_records_budget_id_fkey FOREIGN KEY (budget_id) REFERENCES public.crypto_agent_budgets(id) ON DELETE SET NULL;


--

-- FK CONSTRAINT: ai_inference_records ai_inference_records_tenant_id_fkey
ALTER TABLE ONLY public.ai_inference_records
    ADD CONSTRAINT ai_inference_records_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: ai_inference_records ai_inference_records_user_id_fkey
ALTER TABLE ONLY public.ai_inference_records
    ADD CONSTRAINT ai_inference_records_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: api_keys api_keys_tenant_id_fkey
ALTER TABLE ONLY public.api_keys
    ADD CONSTRAINT api_keys_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: billing_records billing_records_tenant_id_fkey
ALTER TABLE ONLY public.billing_records
    ADD CONSTRAINT billing_records_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: billing_records billing_records_user_id_fkey
ALTER TABLE ONLY public.billing_records
    ADD CONSTRAINT billing_records_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--

-- FK CONSTRAINT: branding_configuration branding_configuration_tenant_id_fkey
ALTER TABLE ONLY public.branding_configuration
    ADD CONSTRAINT branding_configuration_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: chat_histories_ai chat_histories_ai_tenant_id_fkey
ALTER TABLE ONLY public.chat_histories_ai
    ADD CONSTRAINT chat_histories_ai_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: chat_sessions_ai chat_sessions_ai_history_id_fkey
ALTER TABLE ONLY public.chat_sessions_ai
    ADD CONSTRAINT chat_sessions_ai_history_id_fkey FOREIGN KEY (history_id) REFERENCES public.chat_histories_ai(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: chat_sessions_ai chat_sessions_ai_tenant_id_fkey
ALTER TABLE ONLY public.chat_sessions_ai
    ADD CONSTRAINT chat_sessions_ai_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: chat_sessions_ai chat_sessions_ai_user_id_fkey
ALTER TABLE ONLY public.chat_sessions_ai
    ADD CONSTRAINT chat_sessions_ai_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: crypto_agent_budgets crypto_agent_budgets_tenant_id_fkey
ALTER TABLE ONLY public.crypto_agent_budgets
    ADD CONSTRAINT crypto_agent_budgets_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: crypto_agent_budgets crypto_agent_budgets_user_id_fkey
ALTER TABLE ONLY public.crypto_agent_budgets
    ADD CONSTRAINT crypto_agent_budgets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--

-- FK CONSTRAINT: groups groups_role_id_fkey
ALTER TABLE ONLY public.groups
    ADD CONSTRAINT groups_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE RESTRICT;


--

-- FK CONSTRAINT: groups groups_tenant_id_fkey
ALTER TABLE ONLY public.groups
    ADD CONSTRAINT groups_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: marketplace_listings marketplace_listings_seller_id_fkey
ALTER TABLE ONLY public.marketplace_listings
    ADD CONSTRAINT marketplace_listings_seller_id_fkey FOREIGN KEY (seller_id) REFERENCES public.users(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: marketplace_listings marketplace_listings_tenant_id_fkey
ALTER TABLE ONLY public.marketplace_listings
    ADD CONSTRAINT marketplace_listings_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: marketplace_purchases marketplace_purchases_billing_record_id_fkey
ALTER TABLE ONLY public.marketplace_purchases
    ADD CONSTRAINT marketplace_purchases_billing_record_id_fkey FOREIGN KEY (billing_record_id) REFERENCES public.billing_records(id) ON DELETE SET NULL;


--

-- FK CONSTRAINT: marketplace_purchases marketplace_purchases_buyer_id_fkey
ALTER TABLE ONLY public.marketplace_purchases
    ADD CONSTRAINT marketplace_purchases_buyer_id_fkey FOREIGN KEY (buyer_id) REFERENCES public.users(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: marketplace_purchases marketplace_purchases_listing_id_fkey
ALTER TABLE ONLY public.marketplace_purchases
    ADD CONSTRAINT marketplace_purchases_listing_id_fkey FOREIGN KEY (listing_id) REFERENCES public.marketplace_listings(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: marketplace_purchases marketplace_purchases_tenant_id_fkey
ALTER TABLE ONLY public.marketplace_purchases
    ADD CONSTRAINT marketplace_purchases_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: marketplace_seller_profiles marketplace_seller_profiles_tenant_id_fkey
ALTER TABLE ONLY public.marketplace_seller_profiles
    ADD CONSTRAINT marketplace_seller_profiles_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: marketplace_seller_profiles marketplace_seller_profiles_user_id_fkey
ALTER TABLE ONLY public.marketplace_seller_profiles
    ADD CONSTRAINT marketplace_seller_profiles_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: notification_banner_settings notification_banner_settings_tenant_id_fkey
ALTER TABLE ONLY public.notification_banner_settings
    ADD CONSTRAINT notification_banner_settings_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: operator_audit operator_audit_tenant_id_fkey
ALTER TABLE ONLY public.operator_audit
    ADD CONSTRAINT operator_audit_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: operator_bans operator_bans_tenant_id_fkey
ALTER TABLE ONLY public.operator_bans
    ADD CONSTRAINT operator_bans_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: operator_peers operator_peers_tenant_id_fkey
ALTER TABLE ONLY public.operator_peers
    ADD CONSTRAINT operator_peers_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: organization_idp_links organization_idp_links_organization_id_fkey
ALTER TABLE ONLY public.organization_idp_links
    ADD CONSTRAINT organization_idp_links_organization_id_fkey FOREIGN KEY (organization_id) REFERENCES public.organizations(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: organization_idp_links organization_idp_links_tenant_id_fkey
ALTER TABLE ONLY public.organization_idp_links
    ADD CONSTRAINT organization_idp_links_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: organizations organizations_tenant_id_fkey
ALTER TABLE ONLY public.organizations
    ADD CONSTRAINT organizations_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: roles roles_tenant_id_fkey
ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: sociacl_recovery_sessions sociacl_recovery_sessions_tenant_id_fkey
ALTER TABLE ONLY public.sociacl_recovery_sessions
    ADD CONSTRAINT sociacl_recovery_sessions_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: sociacl_share_links sociacl_share_links_group_id_fkey
ALTER TABLE ONLY public.sociacl_share_links
    ADD CONSTRAINT sociacl_share_links_group_id_fkey FOREIGN KEY (group_id) REFERENCES public.groups(id) ON DELETE SET NULL;


--

-- FK CONSTRAINT: sociacl_share_links sociacl_share_links_owner_user_id_fkey
ALTER TABLE ONLY public.sociacl_share_links
    ADD CONSTRAINT sociacl_share_links_owner_user_id_fkey FOREIGN KEY (owner_user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--

-- FK CONSTRAINT: sociacl_share_links sociacl_share_links_tenant_id_fkey
ALTER TABLE ONLY public.sociacl_share_links
    ADD CONSTRAINT sociacl_share_links_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: sso_settings sso_settings_tenant_id_fkey
ALTER TABLE ONLY public.sso_settings
    ADD CONSTRAINT sso_settings_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: storage_settings storage_settings_tenant_id_fkey
ALTER TABLE ONLY public.storage_settings
    ADD CONSTRAINT storage_settings_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: stripe_settings stripe_settings_tenant_id_fkey
ALTER TABLE ONLY public.stripe_settings
    ADD CONSTRAINT stripe_settings_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: subscription_plans subscription_plans_tenant_id_fkey
ALTER TABLE ONLY public.subscription_plans
    ADD CONSTRAINT subscription_plans_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: subscription_plans subscription_plans_user_id_fkey
ALTER TABLE ONLY public.subscription_plans
    ADD CONSTRAINT subscription_plans_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--

-- FK CONSTRAINT: user_group_memberships user_group_memberships_group_id_fkey
ALTER TABLE ONLY public.user_group_memberships
    ADD CONSTRAINT user_group_memberships_group_id_fkey FOREIGN KEY (group_id) REFERENCES public.groups(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: user_group_memberships user_group_memberships_tenant_id_fkey
ALTER TABLE ONLY public.user_group_memberships
    ADD CONSTRAINT user_group_memberships_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: user_group_memberships user_group_memberships_user_id_fkey
ALTER TABLE ONLY public.user_group_memberships
    ADD CONSTRAINT user_group_memberships_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: user_magic_links user_magic_links_tenant_id_fkey
ALTER TABLE ONLY public.user_magic_links
    ADD CONSTRAINT user_magic_links_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: user_magic_links user_magic_links_user_id_fkey
ALTER TABLE ONLY public.user_magic_links
    ADD CONSTRAINT user_magic_links_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: user_passkey_challenges user_passkey_challenges_tenant_id_fkey
ALTER TABLE ONLY public.user_passkey_challenges
    ADD CONSTRAINT user_passkey_challenges_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: user_passkeys user_passkeys_tenant_id_fkey
ALTER TABLE ONLY public.user_passkeys
    ADD CONSTRAINT user_passkeys_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: user_password_resets user_password_resets_tenant_id_fkey
ALTER TABLE ONLY public.user_password_resets
    ADD CONSTRAINT user_password_resets_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: user_password_resets user_password_resets_user_id_fkey
ALTER TABLE ONLY public.user_password_resets
    ADD CONSTRAINT user_password_resets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: user_preferences user_preferences_tenant_id_fkey
ALTER TABLE ONLY public.user_preferences
    ADD CONSTRAINT user_preferences_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: user_preferences user_preferences_user_id_fkey
ALTER TABLE ONLY public.user_preferences
    ADD CONSTRAINT user_preferences_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: users users_role_id_fkey
ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE SET NULL;


--

-- FK CONSTRAINT: users users_tenant_id_fkey
ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- ROW SECURITY: acl_casbin_rules
ALTER TABLE public.acl_casbin_rules ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: ai_agent_entitlements
ALTER TABLE public.ai_agent_entitlements ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: ai_budget_event_audit
ALTER TABLE public.ai_budget_event_audit ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: ai_inference_records
ALTER TABLE public.ai_inference_records ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: billing_records
ALTER TABLE public.billing_records ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: branding_configuration
ALTER TABLE public.branding_configuration ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: chat_histories_ai
ALTER TABLE public.chat_histories_ai ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: chat_sessions_ai
ALTER TABLE public.chat_sessions_ai ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: crypto_agent_budgets
ALTER TABLE public.crypto_agent_budgets ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: groups
ALTER TABLE public.groups ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: marketplace_listings
ALTER TABLE public.marketplace_listings ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: marketplace_purchases
ALTER TABLE public.marketplace_purchases ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: marketplace_seller_profiles
ALTER TABLE public.marketplace_seller_profiles ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: notification_banner_settings
ALTER TABLE public.notification_banner_settings ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: operator_audit
ALTER TABLE public.operator_audit ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: operator_bans
ALTER TABLE public.operator_bans ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: operator_peers
ALTER TABLE public.operator_peers ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: organization_idp_links
ALTER TABLE public.organization_idp_links ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: organizations
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: roles
ALTER TABLE public.roles ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: sociacl_recovery_sessions
ALTER TABLE public.sociacl_recovery_sessions ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: sociacl_share_links
ALTER TABLE public.sociacl_share_links ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: sso_settings
ALTER TABLE public.sso_settings ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: storage_settings
ALTER TABLE public.storage_settings ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: stripe_settings
ALTER TABLE public.stripe_settings ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: subscription_plans
ALTER TABLE public.subscription_plans ENABLE ROW LEVEL SECURITY;

--

-- POLICY: acl_casbin_rules tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.acl_casbin_rules FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: ai_agent_entitlements tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.ai_agent_entitlements FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: ai_budget_event_audit tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.ai_budget_event_audit FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: ai_inference_records tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.ai_inference_records FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: billing_records tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.billing_records FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: branding_configuration tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.branding_configuration FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: chat_histories_ai tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.chat_histories_ai FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: chat_sessions_ai tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.chat_sessions_ai FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: crypto_agent_budgets tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.crypto_agent_budgets FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: groups tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.groups FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: marketplace_listings tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.marketplace_listings FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: marketplace_purchases tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.marketplace_purchases FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: marketplace_seller_profiles tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.marketplace_seller_profiles FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: notification_banner_settings tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.notification_banner_settings FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: operator_audit tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.operator_audit FOR DELETE USING (((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)));


--

-- POLICY: operator_bans tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.operator_bans FOR DELETE USING (((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)));


--

-- POLICY: operator_peers tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.operator_peers FOR DELETE USING (((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)));


--

-- POLICY: organization_idp_links tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.organization_idp_links FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: organizations tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.organizations FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: roles tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.roles FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: sociacl_recovery_sessions tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.sociacl_recovery_sessions FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: sociacl_share_links tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.sociacl_share_links FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: sso_settings tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.sso_settings FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: storage_settings tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.storage_settings FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: stripe_settings tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.stripe_settings FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: subscription_plans tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.subscription_plans FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_group_memberships tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.user_group_memberships FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_magic_links tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.user_magic_links FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_passkey_challenges tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.user_passkey_challenges FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_passkeys tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.user_passkeys FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_password_resets tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.user_password_resets FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_preferences tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.user_preferences FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: users tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.users FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: acl_casbin_rules tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.acl_casbin_rules FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: ai_agent_entitlements tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.ai_agent_entitlements FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: ai_budget_event_audit tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.ai_budget_event_audit FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: ai_inference_records tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.ai_inference_records FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: billing_records tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.billing_records FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: branding_configuration tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.branding_configuration FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: chat_histories_ai tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.chat_histories_ai FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: chat_sessions_ai tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.chat_sessions_ai FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: crypto_agent_budgets tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.crypto_agent_budgets FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: groups tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.groups FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: marketplace_listings tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.marketplace_listings FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: marketplace_purchases tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.marketplace_purchases FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: marketplace_seller_profiles tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.marketplace_seller_profiles FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: notification_banner_settings tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.notification_banner_settings FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: operator_audit tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.operator_audit FOR INSERT WITH CHECK (((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)));


--

-- POLICY: operator_bans tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.operator_bans FOR INSERT WITH CHECK (((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)));


--

-- POLICY: operator_peers tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.operator_peers FOR INSERT WITH CHECK (((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)));


--

-- POLICY: organization_idp_links tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.organization_idp_links FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: organizations tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.organizations FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: roles tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.roles FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: sociacl_recovery_sessions tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.sociacl_recovery_sessions FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: sociacl_share_links tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.sociacl_share_links FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: sso_settings tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.sso_settings FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: storage_settings tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.storage_settings FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: stripe_settings tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.stripe_settings FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: subscription_plans tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.subscription_plans FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_group_memberships tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.user_group_memberships FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_magic_links tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.user_magic_links FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_passkey_challenges tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.user_passkey_challenges FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_passkeys tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.user_passkeys FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_password_resets tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.user_password_resets FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_preferences tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.user_preferences FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: users tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.users FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: acl_casbin_rules tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.acl_casbin_rules FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: ai_agent_entitlements tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.ai_agent_entitlements FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: ai_budget_event_audit tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.ai_budget_event_audit FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: ai_inference_records tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.ai_inference_records FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: billing_records tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.billing_records FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: branding_configuration tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.branding_configuration FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: chat_histories_ai tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.chat_histories_ai FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: chat_sessions_ai tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.chat_sessions_ai FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: crypto_agent_budgets tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.crypto_agent_budgets FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: groups tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.groups FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: marketplace_listings tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.marketplace_listings FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: marketplace_purchases tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.marketplace_purchases FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: marketplace_seller_profiles tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.marketplace_seller_profiles FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: notification_banner_settings tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.notification_banner_settings FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: operator_audit tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.operator_audit FOR SELECT USING (((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)));


--

-- POLICY: operator_bans tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.operator_bans FOR SELECT USING (((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)));


--

-- POLICY: operator_peers tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.operator_peers FOR SELECT USING (((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)));


--

-- POLICY: organization_idp_links tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.organization_idp_links FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: organizations tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.organizations FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: roles tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.roles FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: sociacl_recovery_sessions tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.sociacl_recovery_sessions FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: sociacl_share_links tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.sociacl_share_links FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: sso_settings tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.sso_settings FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: storage_settings tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.storage_settings FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: stripe_settings tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.stripe_settings FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: subscription_plans tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.subscription_plans FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_group_memberships tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.user_group_memberships FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_magic_links tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.user_magic_links FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_passkey_challenges tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.user_passkey_challenges FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_passkeys tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.user_passkeys FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_password_resets tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.user_password_resets FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_preferences tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.user_preferences FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: users tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.users FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: acl_casbin_rules tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.acl_casbin_rules FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: ai_agent_entitlements tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.ai_agent_entitlements FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: ai_budget_event_audit tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.ai_budget_event_audit FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: ai_inference_records tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.ai_inference_records FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: billing_records tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.billing_records FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: branding_configuration tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.branding_configuration FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: chat_histories_ai tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.chat_histories_ai FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: chat_sessions_ai tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.chat_sessions_ai FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: crypto_agent_budgets tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.crypto_agent_budgets FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: groups tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.groups FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: marketplace_listings tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.marketplace_listings FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: marketplace_purchases tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.marketplace_purchases FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: marketplace_seller_profiles tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.marketplace_seller_profiles FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: notification_banner_settings tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.notification_banner_settings FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: operator_audit tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.operator_audit FOR UPDATE USING (((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))) WITH CHECK (((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)));


--

-- POLICY: operator_bans tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.operator_bans FOR UPDATE USING (((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))) WITH CHECK (((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)));


--

-- POLICY: operator_peers tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.operator_peers FOR UPDATE USING (((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))) WITH CHECK (((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)));


--

-- POLICY: organization_idp_links tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.organization_idp_links FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: organizations tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.organizations FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: roles tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.roles FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: sociacl_recovery_sessions tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.sociacl_recovery_sessions FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: sociacl_share_links tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.sociacl_share_links FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: sso_settings tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.sso_settings FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: storage_settings tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.storage_settings FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: stripe_settings tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.stripe_settings FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: subscription_plans tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.subscription_plans FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_group_memberships tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.user_group_memberships FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_magic_links tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.user_magic_links FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_passkey_challenges tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.user_passkey_challenges FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_passkeys tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.user_passkeys FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_password_resets tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.user_password_resets FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: user_preferences tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.user_preferences FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: users tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.users FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- ROW SECURITY: user_group_memberships
ALTER TABLE public.user_group_memberships ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: user_magic_links
ALTER TABLE public.user_magic_links ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: user_passkey_challenges
ALTER TABLE public.user_passkey_challenges ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: user_passkeys
ALTER TABLE public.user_passkeys ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: user_password_resets
ALTER TABLE public.user_password_resets ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: user_preferences
ALTER TABLE public.user_preferences ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: users
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

--
