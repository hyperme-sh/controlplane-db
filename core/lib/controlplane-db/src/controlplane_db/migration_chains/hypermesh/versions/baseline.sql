-- Frozen schema-only baseline at 0053_onboarding_runs. No seed data.
SET LOCAL search_path = public, pg_catalog;
SET LOCAL check_function_bodies = false;

-- TABLE: host_organization_bindings
CREATE TABLE public.host_organization_bindings (
    tenant_id uuid NOT NULL,
    keycloak_sub character varying(512) NOT NULL,
    organization_id uuid NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);

ALTER TABLE ONLY public.host_organization_bindings FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_auditor_tickets
CREATE TABLE public.hypermesh_auditor_tickets (
    ticket_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    site_id character varying(128) NOT NULL,
    ticket_schema character varying(64) NOT NULL,
    trace_id uuid NOT NULL,
    receipt_id uuid,
    held_call_id uuid NOT NULL,
    reason_code character varying(64) NOT NULL,
    severity character varying(16) NOT NULL,
    text_redacted character varying(1000) NOT NULL,
    display jsonb NOT NULL,
    status character varying(16) NOT NULL,
    resolution character varying(16),
    resolved_by character varying(256),
    resolved_at timestamp with time zone,
    patch jsonb,
    notes_redacted character varying(1000),
    site_acked_receipt_id uuid,
    created_at timestamp with time zone NOT NULL
);

ALTER TABLE ONLY public.hypermesh_auditor_tickets FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_catalog
CREATE TABLE public.hypermesh_catalog (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    catalog_id character varying(64) NOT NULL,
    artifact_name character varying(256) NOT NULL,
    class_id character varying(64) NOT NULL,
    file_hash character varying(256),
    image_digest character varying(256),
    quant character varying(32),
    format character varying(32),
    runtime character varying(64),
    advertised_context integer,
    certified boolean NOT NULL,
    tokens_per_sec double precision,
    per_1k_token_cents integer NOT NULL,
    loaded_hour_min_cents integer NOT NULL,
    origin character varying(16) DEFAULT 'seed'::character varying NOT NULL,
    admission_id uuid,
    size_bytes bigint,
    onboarding_source_ref character varying(1024)
);

ALTER TABLE ONLY public.hypermesh_catalog FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_cost_inputs
CREATE TABLE public.hypermesh_cost_inputs (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    device_id uuid,
    class_id character varying(64),
    capex_cents integer NOT NULL,
    loaded_kw numeric NOT NULL,
    tariff_cents_per_kwh integer NOT NULL,
    overhead numeric NOT NULL,
    residual numeric NOT NULL,
    host_margin numeric NOT NULL,
    processor_pct numeric,
    processor_fixed_cents integer,
    expected_hours_per_txn numeric,
    source character varying(64) NOT NULL,
    effective_from timestamp with time zone NOT NULL,
    CONSTRAINT ck_hm_pricing_cost_nonneg CHECK (((capex_cents >= 0) AND (tariff_cents_per_kwh >= 0) AND (loaded_kw >= (0)::numeric))),
    CONSTRAINT ck_hm_pricing_cost_processor CHECK (((processor_fixed_cents IS NULL) OR (processor_fixed_cents >= 0))),
    CONSTRAINT ck_hm_pricing_cost_scope CHECK ((((device_id IS NOT NULL) AND (class_id IS NULL)) OR ((device_id IS NULL) AND (class_id IS NOT NULL))))
);

ALTER TABLE ONLY public.hypermesh_cost_inputs FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_device_health
CREATE TABLE public.hypermesh_device_health (
    device_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    tunnel_state character varying(32),
    last_sync_at timestamp with time zone,
    last_sync_error_class character varying(64),
    last_sync_http_status integer,
    handshake_age_s integer,
    wg_pid integer,
    wg_port integer,
    lease_container_count integer,
    build_commit character varying(64),
    disk_free_bytes bigint,
    model_cache_evictable_bytes bigint,
    received_at timestamp with time zone NOT NULL,
    sync_error_since timestamp with time zone,
    CONSTRAINT ck_hm_health_build_commit CHECK (((build_commit IS NULL) OR ((build_commit)::text ~ '^[0-9a-f]{1,64}$'::text))),
    CONSTRAINT ck_hm_health_cache_evictable CHECK (((model_cache_evictable_bytes IS NULL) OR (model_cache_evictable_bytes >= 0))),
    CONSTRAINT ck_hm_health_containers CHECK (((lease_container_count IS NULL) OR (lease_container_count >= 0))),
    CONSTRAINT ck_hm_health_disk_free CHECK (((disk_free_bytes IS NULL) OR (disk_free_bytes >= 0))),
    CONSTRAINT ck_hm_health_handshake CHECK (((handshake_age_s IS NULL) OR (handshake_age_s >= 0))),
    CONSTRAINT ck_hm_health_http_status CHECK (((last_sync_http_status IS NULL) OR ((last_sync_http_status >= 0) AND (last_sync_http_status <= 599)))),
    CONSTRAINT ck_hm_health_wg_pid CHECK (((wg_pid IS NULL) OR (wg_pid >= 0))),
    CONSTRAINT ck_hm_health_wg_port CHECK (((wg_port IS NULL) OR ((wg_port >= 1) AND (wg_port <= 65535))))
);

ALTER TABLE ONLY public.hypermesh_device_health FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_devices
CREATE TABLE public.hypermesh_devices (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    class_id character varying(64) NOT NULL,
    host_org_id uuid NOT NULL,
    host_name character varying(128),
    archived_at timestamp with time zone,
    serial character varying(128) NOT NULL,
    path_a jsonb NOT NULL,
    path_b_state character varying(32) NOT NULL,
    loaded_instance_state character varying(32) NOT NULL,
    loaded_catalog_id character varying(64),
    enroll_token_hash character varying(64),
    enroll_token_used_hash character varying(64),
    enroll_token_prefix character varying(16),
    device_secret_hash character varying(64),
    credential_prefix character varying(16),
    enrolled boolean NOT NULL,
    last_heartbeat_at timestamp with time zone,
    last_path_b_at timestamp with time zone,
    last_image_hash character varying(128),
    last_loaded_model_hash character varying(128),
    last_uptime_s integer,
    last_thermal_c numeric,
    usdc_pubkey character varying(64),
    created_at timestamp with time zone NOT NULL,
    sell_state character varying(16) NOT NULL,
    site_id character varying(128),
    role character varying(16) NOT NULL,
    host_type character varying(16) DEFAULT 'model'::character varying NOT NULL,
    schedule_hold boolean DEFAULT false NOT NULL,
    lab boolean DEFAULT false NOT NULL,
    wg_public_key character varying(128)
);

ALTER TABLE ONLY public.hypermesh_devices FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_fills
CREATE TABLE public.hypermesh_fills (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    round_id character varying(128) NOT NULL,
    order_id character varying(128) NOT NULL,
    pool_id character varying(129) NOT NULL,
    org_id character varying(128) NOT NULL,
    rung_index integer NOT NULL,
    hours numeric NOT NULL,
    device_id uuid,
    lease_id uuid,
    pay_cents integer NOT NULL,
    total_cents integer NOT NULL,
    tip_cents integer NOT NULL,
    lock_until timestamp with time zone NOT NULL,
    ruleset_version character varying(64) NOT NULL,
    engine_version character varying(32) NOT NULL,
    CONSTRAINT ck_hm_pricing_fill_money CHECK (((pay_cents >= 0) AND (total_cents >= 0) AND (tip_cents >= 0) AND (hours > (0)::numeric))),
    CONSTRAINT ck_hm_pricing_fill_versions CHECK (((char_length((ruleset_version)::text) > 0) AND (char_length((engine_version)::text) > 0)))
);

ALTER TABLE ONLY public.hypermesh_fills FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_fleet_alerts
CREATE TABLE public.hypermesh_fleet_alerts (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    device_id uuid NOT NULL,
    kind character varying(32) NOT NULL,
    state character varying(16) NOT NULL,
    first_seen timestamp with time zone NOT NULL,
    last_seen timestamp with time zone NOT NULL,
    resolved_at timestamp with time zone,
    detail character varying(256),
    CONSTRAINT ck_hm_fleet_alert_kind CHECK (kind IN ('heartbeat_stale', 'handshake_stale', 'tunnel_sync_failing', 'build_drift')),
    CONSTRAINT ck_hm_fleet_alert_state CHECK (state IN ('open', 'resolved'))
);

ALTER TABLE ONLY public.hypermesh_fleet_alerts FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_fleet_health_config
CREATE TABLE public.hypermesh_fleet_health_config (
    tenant_id uuid NOT NULL,
    heartbeat_stale_s integer NOT NULL,
    handshake_stale_s integer NOT NULL,
    sync_fail_s integer NOT NULL,
    expected_build_commit character varying(64),
    CONSTRAINT ck_hm_fleet_cfg_commit CHECK (((expected_build_commit IS NULL) OR ((expected_build_commit)::text ~ '^[0-9a-f]{1,64}$'::text))),
    CONSTRAINT ck_hm_fleet_cfg_handshake CHECK ((handshake_stale_s >= 1)),
    CONSTRAINT ck_hm_fleet_cfg_heartbeat CHECK ((heartbeat_stale_s >= 1)),
    CONSTRAINT ck_hm_fleet_cfg_sync CHECK ((sync_fail_s >= 1))
);

ALTER TABLE ONLY public.hypermesh_fleet_health_config FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_gateway_metrics
CREATE TABLE public.hypermesh_gateway_metrics (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    gateway_id uuid NOT NULL,
    tunnel_id uuid,
    lease_id uuid,
    bytes_in bigint NOT NULL,
    bytes_out bigint NOT NULL,
    handshake_count integer NOT NULL,
    recorded_at timestamp with time zone NOT NULL
);

ALTER TABLE ONLY public.hypermesh_gateway_metrics FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_gateways
CREATE TABLE public.hypermesh_gateways (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    name character varying(128) NOT NULL,
    secret_hash character varying(64),
    credential_prefix character varying(16),
    role character varying(16) DEFAULT 'gateway'::character varying NOT NULL,
    created_at timestamp with time zone NOT NULL
);

ALTER TABLE ONLY public.hypermesh_gateways FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_hardware_classes
CREATE TABLE public.hypermesh_hardware_classes (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    class_id character varying(64) NOT NULL,
    vendor character varying(64) NOT NULL,
    sku character varying(128) NOT NULL,
    module character varying(64) NOT NULL,
    memory_gb integer NOT NULL,
    public_sku boolean NOT NULL,
    path_b_suite_id character varying(64) NOT NULL,
    hourly_rate_cents integer NOT NULL,
    advertised_envelope text
);

ALTER TABLE ONLY public.hypermesh_hardware_classes FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_host_cert_overrides
CREATE TABLE public.hypermesh_host_cert_overrides (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    device_id uuid NOT NULL,
    status character varying(16) NOT NULL,
    preempt boolean NOT NULL,
    preempted_lease_id uuid,
    lease_stop_job_id uuid,
    cert_job_id uuid,
    held_at timestamp with time zone NOT NULL,
    restored_at timestamp with time zone,
    completed_at timestamp with time zone,
    fail_closed boolean NOT NULL,
    created_at timestamp with time zone NOT NULL
);

ALTER TABLE ONLY public.hypermesh_host_cert_overrides FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_host_registrations
CREATE TABLE public.hypermesh_host_registrations (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    owner_sub character varying(512) NOT NULL,
    host_org_id uuid NOT NULL,
    request jsonb NOT NULL,
    enrollment_event jsonb,
    event_forwarded_at timestamp with time zone,
    state character varying(16) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    decided_at timestamp with time zone,
    device_id uuid,
    CONSTRAINT ck_hm_registration_state CHECK (state IN ('pending', 'approved', 'denied', 'completed'))
);

ALTER TABLE ONLY public.hypermesh_host_registrations FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_jobs
CREATE TABLE public.hypermesh_jobs (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    device_id uuid NOT NULL,
    suite_id character varying(64),
    kind character varying(32) NOT NULL,
    status character varying(32) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    completed_at timestamp with time zone,
    image_hash character varying(256),
    lease_id uuid,
    catalog_id character varying(64),
    image_digest character varying(256),
    source_ref character varying(512),
    runtime character varying(64),
    ticket text,
    until timestamp with time zone,
    sell_state character varying(16),
    dispatch_skip_reason character varying(256)
);

ALTER TABLE ONLY public.hypermesh_jobs FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_lease_audit
CREATE TABLE public.hypermesh_lease_audit (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    lease_id uuid NOT NULL,
    status character varying(32) NOT NULL,
    kind character varying(32) NOT NULL,
    class_id character varying(64) NOT NULL,
    catalog_id character varying(64),
    recorded_at timestamp with time zone NOT NULL,
    reason character varying(128)
);

ALTER TABLE ONLY public.hypermesh_lease_audit FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_leases
CREATE TABLE public.hypermesh_leases (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    kind character varying(32) NOT NULL,
    status character varying(32) NOT NULL,
    renter_user_id uuid NOT NULL,
    class_id character varying(64) NOT NULL,
    catalog_id character varying(64),
    device_id uuid,
    host_org_id uuid,
    reserved_hours integer NOT NULL,
    billing_record_id uuid,
    stripe_session_id character varying(255),
    checkout_url text,
    gross_cents integer,
    token_count integer NOT NULL,
    loaded_hours integer NOT NULL,
    created_at timestamp with time zone NOT NULL,
    activated_at timestamp with time zone,
    ended_at timestamp with time zone,
    failed_at timestamp with time zone,
    purpose character varying(32) NOT NULL,
    contract_id uuid,
    ruleset_version character varying(64)
);

ALTER TABLE ONLY public.hypermesh_leases FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_onboarding_runs
CREATE TABLE public.hypermesh_onboarding_runs (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    device_id uuid NOT NULL,
    registration_id uuid NOT NULL,
    manifest jsonb NOT NULL,
    manifest_sha256 character varying(64) NOT NULL,
    state character varying(16) NOT NULL,
    evidence jsonb,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    completed_at timestamp with time zone,
    approved_by character varying(512),
    approved_at timestamp with time zone,
    CONSTRAINT ck_hm_onboarding_state CHECK (state IN ('planned', 'passed', 'failed'))
);

ALTER TABLE ONLY public.hypermesh_onboarding_runs FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_orders
CREATE TABLE public.hypermesh_orders (
    order_id character varying(128) NOT NULL,
    tenant_id uuid NOT NULL,
    org_id character varying(128) NOT NULL,
    pool_id character varying(129) NOT NULL,
    rungs jsonb NOT NULL,
    tip_cents integer NOT NULL,
    hours numeric NOT NULL,
    pain jsonb,
    status character varying(16) NOT NULL,
    prepay_ref character varying(255),
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_hm_pricing_order_money CHECK (((tip_cents >= 0) AND (hours > (0)::numeric))),
    CONSTRAINT ck_hm_pricing_order_status CHECK (status IN ('open', 'filled', 'partial', 'unfilled', 'cancelled'))
);

ALTER TABLE ONLY public.hypermesh_orders FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_payouts
CREATE TABLE public.hypermesh_payouts (
    lease_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    host_org_id uuid NOT NULL,
    host_pubkey character varying(128) NOT NULL,
    kind character varying(32) NOT NULL,
    gross_cents integer NOT NULL,
    stripe_cut_cents integer NOT NULL,
    platform_take_cents integer NOT NULL,
    take_bps integer NOT NULL,
    net_cents integer NOT NULL,
    net_usdc_atoms bigint NOT NULL
);

ALTER TABLE ONLY public.hypermesh_payouts FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_pool_prices
CREATE TABLE public.hypermesh_pool_prices (
    round_id character varying(128) NOT NULL,
    pool_id character varying(129) NOT NULL,
    tenant_id uuid NOT NULL,
    base_cents integer NOT NULL,
    next_base_cents integer NOT NULL,
    floor_cents integer,
    reserve_cents integer NOT NULL,
    cap_cents integer NOT NULL,
    utilization numeric NOT NULL,
    demand_hours numeric NOT NULL,
    supply_hours numeric NOT NULL,
    supply_clamped boolean NOT NULL,
    reserve_source character varying(64) NOT NULL,
    rationed boolean NOT NULL,
    boost_active boolean NOT NULL,
    boost_multiple numeric NOT NULL,
    at_cap boolean NOT NULL,
    at_floor boolean NOT NULL,
    scarce boolean NOT NULL,
    org_cap_applied boolean NOT NULL,
    degraded boolean NOT NULL,
    ruleset_version character varying(64) NOT NULL,
    boost jsonb NOT NULL,
    next_ema_cents integer NOT NULL,
    trailing_state jsonb NOT NULL,
    supply_tiers jsonb,
    CONSTRAINT ck_hm_pool_price_cents CHECK (((base_cents >= 0) AND (next_base_cents >= 0) AND (reserve_cents >= 0) AND (cap_cents >= 0) AND (next_ema_cents >= 0) AND ((floor_cents IS NULL) OR (floor_cents >= 0)))),
    CONSTRAINT ck_hm_pool_price_ruleset CHECK ((char_length((ruleset_version)::text) > 0))
);

ALTER TABLE ONLY public.hypermesh_pool_prices FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_pricing_alerts
CREATE TABLE public.hypermesh_pricing_alerts (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    pool_id character varying(129),
    device_id uuid,
    kind character varying(32) NOT NULL,
    state character varying(16) NOT NULL,
    first_seen timestamp with time zone NOT NULL,
    last_seen timestamp with time zone NOT NULL,
    resolved_at timestamp with time zone,
    detail character varying(256),
    CONSTRAINT ck_hm_pricing_alert_kind CHECK (kind IN ('degraded_rounds', 'engine_unreachable')),
    CONSTRAINT ck_hm_pricing_alert_scope CHECK (((pool_id IS NOT NULL) OR (device_id IS NOT NULL))),
    CONSTRAINT ck_hm_pricing_alert_state CHECK (state IN ('open', 'resolved'))
);

ALTER TABLE ONLY public.hypermesh_pricing_alerts FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_pricing_pools
CREATE TABLE public.hypermesh_pricing_pools (
    pool_id character varying(129) NOT NULL,
    tenant_id uuid NOT NULL,
    class_id character varying(64) NOT NULL,
    region character varying(64) DEFAULT 'default'::character varying NOT NULL,
    kind character varying(2) NOT NULL,
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_hm_pricing_pool_id_shape CHECK (((pool_id)::text = (((class_id)::text || '@'::text) || (region)::text))),
    CONSTRAINT ck_hm_pricing_pool_kind CHECK (kind IN ('P1', 'P2'))
);

ALTER TABLE ONLY public.hypermesh_pricing_pools FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_pricing_rounds
CREATE TABLE public.hypermesh_pricing_rounds (
    round_id character varying(128) NOT NULL,
    tenant_id uuid NOT NULL,
    round_start timestamp with time zone NOT NULL,
    round_type character varying(16) NOT NULL,
    ruleset_version character varying(64) NOT NULL,
    engine_version character varying(32) NOT NULL,
    degraded boolean NOT NULL,
    request_hash character varying(64) NOT NULL,
    idempotency_key character varying(128) NOT NULL,
    lottery_seed_commit character varying(64) NOT NULL,
    lottery_seed character varying(128),
    created_at timestamp with time zone NOT NULL,
    CONSTRAINT ck_hm_pricing_round_engine CHECK ((char_length((engine_version)::text) > 0)),
    CONSTRAINT ck_hm_pricing_round_request_hash CHECK (((request_hash)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_hm_pricing_round_ruleset CHECK ((char_length((ruleset_version)::text) > 0)),
    CONSTRAINT ck_hm_pricing_round_seed CHECK (((lottery_seed IS NULL) OR ((lottery_seed)::text ~ '^[0-9a-f]{1,128}$'::text))),
    CONSTRAINT ck_hm_pricing_round_seed_commit CHECK (((lottery_seed_commit)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT ck_hm_pricing_round_type CHECK (round_type IN ('realtime', 'day_ahead'))
);

ALTER TABLE ONLY public.hypermesh_pricing_rounds FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_privilege_grants
CREATE TABLE public.hypermesh_privilege_grants (
    grant_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    site_id character varying(128) NOT NULL,
    grant_schema character varying(64) NOT NULL,
    incident_id uuid NOT NULL,
    trace_id uuid NOT NULL,
    requested_at timestamp with time zone NOT NULL,
    requested_by jsonb NOT NULL,
    reason_redacted character varying(1000) NOT NULL,
    asks jsonb NOT NULL,
    rails_profile_requested character varying(32),
    ttl_s_requested integer NOT NULL,
    blast_radius character varying(16) NOT NULL,
    status character varying(16) NOT NULL,
    resolution jsonb,
    active_until timestamp with time zone,
    parent_grant_id uuid,
    ticket_id uuid,
    integrity jsonb,
    idempotency_key character varying(128)
);

ALTER TABLE ONLY public.hypermesh_privilege_grants FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_revoked_tickets
CREATE TABLE public.hypermesh_revoked_tickets (
    lease_id uuid NOT NULL,
    tenant_id uuid NOT NULL
);

ALTER TABLE ONLY public.hypermesh_revoked_tickets FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_scorecards
CREATE TABLE public.hypermesh_scorecards (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    device_id uuid NOT NULL,
    catalog_id character varying(64) NOT NULL,
    class_id character varying(64) NOT NULL,
    serial character varying(128) NOT NULL,
    image_hash character varying(128) NOT NULL,
    runtime character varying(64) NOT NULL,
    prompt_pack character varying(64) NOT NULL,
    image_digest character varying(256),
    host_version character varying(128),
    source_repo character varying(256),
    source_commit character varying(64),
    source_path character varying(512),
    content_sha256 character varying(64),
    sample_ms integer,
    decode_tok_s double precision,
    sustained boolean NOT NULL,
    thermal_c double precision,
    recorded_at timestamp with time zone NOT NULL
);

ALTER TABLE ONLY public.hypermesh_scorecards FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_site_tokens
CREATE TABLE public.hypermesh_site_tokens (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    site_id character varying(128) NOT NULL,
    secret_hash character varying(64) NOT NULL,
    credential_prefix character varying(16),
    name character varying(256),
    created_by_sub character varying(512),
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone,
    revoked_at timestamp with time zone
);

ALTER TABLE ONLY public.hypermesh_site_tokens FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_tickets
CREATE TABLE public.hypermesh_tickets (
    lease_id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    device_id uuid NOT NULL,
    assigned_gateway_id uuid NOT NULL,
    client_address character varying(64) NOT NULL,
    status character varying(32) NOT NULL,
    exp timestamp with time zone NOT NULL,
    ticket text NOT NULL,
    purpose character varying(32) NOT NULL
);

ALTER TABLE ONLY public.hypermesh_tickets FORCE ROW LEVEL SECURITY;


--

-- TABLE: hypermesh_tunnels
CREATE TABLE public.hypermesh_tunnels (
    id uuid NOT NULL,
    tenant_id uuid NOT NULL,
    lease_id uuid,
    device_id uuid NOT NULL,
    assigned_gateway_id uuid,
    status character varying(32) NOT NULL,
    endpoint character varying(256) NOT NULL,
    server_public_key character varying(128) NOT NULL,
    server_private_key character varying(128),
    peer_public_key character varying(128),
    peer_private_key character varying(128),
    allowed_ips character varying(64) NOT NULL,
    client_address character varying(64) NOT NULL,
    ack_applied boolean NOT NULL,
    created_at timestamp with time zone NOT NULL,
    expires_at timestamp with time zone
);

ALTER TABLE ONLY public.hypermesh_tunnels FORCE ROW LEVEL SECURITY;


--

-- CONSTRAINT: host_organization_bindings host_organization_bindings_pkey
ALTER TABLE ONLY public.host_organization_bindings
    ADD CONSTRAINT host_organization_bindings_pkey PRIMARY KEY (tenant_id, keycloak_sub);


--

-- CONSTRAINT: hypermesh_auditor_tickets hypermesh_auditor_tickets_pkey
ALTER TABLE ONLY public.hypermesh_auditor_tickets
    ADD CONSTRAINT hypermesh_auditor_tickets_pkey PRIMARY KEY (ticket_id);


--

-- CONSTRAINT: hypermesh_catalog hypermesh_catalog_pkey
ALTER TABLE ONLY public.hypermesh_catalog
    ADD CONSTRAINT hypermesh_catalog_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: hypermesh_cost_inputs hypermesh_cost_inputs_pkey
ALTER TABLE ONLY public.hypermesh_cost_inputs
    ADD CONSTRAINT hypermesh_cost_inputs_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: hypermesh_device_health hypermesh_device_health_pkey
ALTER TABLE ONLY public.hypermesh_device_health
    ADD CONSTRAINT hypermesh_device_health_pkey PRIMARY KEY (device_id);


--

-- CONSTRAINT: hypermesh_devices hypermesh_devices_pkey
ALTER TABLE ONLY public.hypermesh_devices
    ADD CONSTRAINT hypermesh_devices_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: hypermesh_fills hypermesh_fills_pkey
ALTER TABLE ONLY public.hypermesh_fills
    ADD CONSTRAINT hypermesh_fills_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: hypermesh_fleet_alerts hypermesh_fleet_alerts_pkey
ALTER TABLE ONLY public.hypermesh_fleet_alerts
    ADD CONSTRAINT hypermesh_fleet_alerts_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: hypermesh_fleet_health_config hypermesh_fleet_health_config_pkey
ALTER TABLE ONLY public.hypermesh_fleet_health_config
    ADD CONSTRAINT hypermesh_fleet_health_config_pkey PRIMARY KEY (tenant_id);


--

-- CONSTRAINT: hypermesh_gateway_metrics hypermesh_gateway_metrics_pkey
ALTER TABLE ONLY public.hypermesh_gateway_metrics
    ADD CONSTRAINT hypermesh_gateway_metrics_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: hypermesh_gateways hypermesh_gateways_pkey
ALTER TABLE ONLY public.hypermesh_gateways
    ADD CONSTRAINT hypermesh_gateways_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: hypermesh_hardware_classes hypermesh_hardware_classes_pkey
ALTER TABLE ONLY public.hypermesh_hardware_classes
    ADD CONSTRAINT hypermesh_hardware_classes_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: hypermesh_host_cert_overrides hypermesh_host_cert_overrides_pkey
ALTER TABLE ONLY public.hypermesh_host_cert_overrides
    ADD CONSTRAINT hypermesh_host_cert_overrides_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: hypermesh_host_registrations hypermesh_host_registrations_device_id_key
ALTER TABLE ONLY public.hypermesh_host_registrations
    ADD CONSTRAINT hypermesh_host_registrations_device_id_key UNIQUE (device_id);


--

-- CONSTRAINT: hypermesh_host_registrations hypermesh_host_registrations_pkey
ALTER TABLE ONLY public.hypermesh_host_registrations
    ADD CONSTRAINT hypermesh_host_registrations_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: hypermesh_jobs hypermesh_jobs_pkey
ALTER TABLE ONLY public.hypermesh_jobs
    ADD CONSTRAINT hypermesh_jobs_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: hypermesh_lease_audit hypermesh_lease_audit_pkey
ALTER TABLE ONLY public.hypermesh_lease_audit
    ADD CONSTRAINT hypermesh_lease_audit_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: hypermesh_leases hypermesh_leases_pkey
ALTER TABLE ONLY public.hypermesh_leases
    ADD CONSTRAINT hypermesh_leases_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: hypermesh_onboarding_runs hypermesh_onboarding_runs_pkey
ALTER TABLE ONLY public.hypermesh_onboarding_runs
    ADD CONSTRAINT hypermesh_onboarding_runs_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: hypermesh_orders hypermesh_orders_pkey
ALTER TABLE ONLY public.hypermesh_orders
    ADD CONSTRAINT hypermesh_orders_pkey PRIMARY KEY (order_id);


--

-- CONSTRAINT: hypermesh_payouts hypermesh_payouts_pkey
ALTER TABLE ONLY public.hypermesh_payouts
    ADD CONSTRAINT hypermesh_payouts_pkey PRIMARY KEY (lease_id);


--

-- CONSTRAINT: hypermesh_pool_prices hypermesh_pool_prices_pkey
ALTER TABLE ONLY public.hypermesh_pool_prices
    ADD CONSTRAINT hypermesh_pool_prices_pkey PRIMARY KEY (round_id, pool_id);


--

-- CONSTRAINT: hypermesh_pricing_alerts hypermesh_pricing_alerts_pkey
ALTER TABLE ONLY public.hypermesh_pricing_alerts
    ADD CONSTRAINT hypermesh_pricing_alerts_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: hypermesh_pricing_pools hypermesh_pricing_pools_pkey
ALTER TABLE ONLY public.hypermesh_pricing_pools
    ADD CONSTRAINT hypermesh_pricing_pools_pkey PRIMARY KEY (pool_id);


--

-- CONSTRAINT: hypermesh_pricing_rounds hypermesh_pricing_rounds_pkey
ALTER TABLE ONLY public.hypermesh_pricing_rounds
    ADD CONSTRAINT hypermesh_pricing_rounds_pkey PRIMARY KEY (round_id);


--

-- CONSTRAINT: hypermesh_privilege_grants hypermesh_privilege_grants_pkey
ALTER TABLE ONLY public.hypermesh_privilege_grants
    ADD CONSTRAINT hypermesh_privilege_grants_pkey PRIMARY KEY (grant_id);


--

-- CONSTRAINT: hypermesh_revoked_tickets hypermesh_revoked_tickets_pkey
ALTER TABLE ONLY public.hypermesh_revoked_tickets
    ADD CONSTRAINT hypermesh_revoked_tickets_pkey PRIMARY KEY (lease_id);


--

-- CONSTRAINT: hypermesh_scorecards hypermesh_scorecards_pkey
ALTER TABLE ONLY public.hypermesh_scorecards
    ADD CONSTRAINT hypermesh_scorecards_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: hypermesh_site_tokens hypermesh_site_tokens_pkey
ALTER TABLE ONLY public.hypermesh_site_tokens
    ADD CONSTRAINT hypermesh_site_tokens_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: hypermesh_tickets hypermesh_tickets_pkey
ALTER TABLE ONLY public.hypermesh_tickets
    ADD CONSTRAINT hypermesh_tickets_pkey PRIMARY KEY (lease_id);


--

-- CONSTRAINT: hypermesh_tunnels hypermesh_tunnels_pkey
ALTER TABLE ONLY public.hypermesh_tunnels
    ADD CONSTRAINT hypermesh_tunnels_pkey PRIMARY KEY (id);


--

-- CONSTRAINT: hypermesh_catalog uq_hm_catalog_tenant_id
ALTER TABLE ONLY public.hypermesh_catalog
    ADD CONSTRAINT uq_hm_catalog_tenant_id UNIQUE (tenant_id, catalog_id);


--

-- CONSTRAINT: hypermesh_gateways uq_hm_gateways_tenant_name
ALTER TABLE ONLY public.hypermesh_gateways
    ADD CONSTRAINT uq_hm_gateways_tenant_name UNIQUE (tenant_id, name);


--

-- CONSTRAINT: hypermesh_hardware_classes uq_hm_hw_class_tenant_id
ALTER TABLE ONLY public.hypermesh_hardware_classes
    ADD CONSTRAINT uq_hm_hw_class_tenant_id UNIQUE (tenant_id, class_id);


--

-- CONSTRAINT: hypermesh_fills uq_hm_pricing_fill_natural
ALTER TABLE ONLY public.hypermesh_fills
    ADD CONSTRAINT uq_hm_pricing_fill_natural UNIQUE (round_id, order_id, pool_id, rung_index);


--

-- CONSTRAINT: hypermesh_pricing_rounds uq_hm_pricing_round_idempotency
ALTER TABLE ONLY public.hypermesh_pricing_rounds
    ADD CONSTRAINT uq_hm_pricing_round_idempotency UNIQUE (tenant_id, idempotency_key);


--

-- CONSTRAINT: hypermesh_scorecards uq_hm_scorecard_device_catalog
ALTER TABLE ONLY public.hypermesh_scorecards
    ADD CONSTRAINT uq_hm_scorecard_device_catalog UNIQUE (tenant_id, device_id, catalog_id);


--

-- CONSTRAINT: hypermesh_site_tokens uq_hm_site_tokens_secret_hash
ALTER TABLE ONLY public.hypermesh_site_tokens
    ADD CONSTRAINT uq_hm_site_tokens_secret_hash UNIQUE (secret_hash);


--

-- CONSTRAINT: host_organization_bindings uq_host_org_binding_organization
ALTER TABLE ONLY public.host_organization_bindings
    ADD CONSTRAINT uq_host_org_binding_organization UNIQUE (organization_id);


--

-- INDEX: ix_hm_auditor_tickets_tenant
CREATE INDEX ix_hm_auditor_tickets_tenant ON public.hypermesh_auditor_tickets USING btree (tenant_id);


--

-- INDEX: ix_hm_auditor_tickets_tenant_site
CREATE INDEX ix_hm_auditor_tickets_tenant_site ON public.hypermesh_auditor_tickets USING btree (tenant_id, site_id);


--

-- INDEX: ix_hm_catalog_tenant
CREATE INDEX ix_hm_catalog_tenant ON public.hypermesh_catalog USING btree (tenant_id);


--

-- INDEX: ix_hm_device_health_tenant
CREATE INDEX ix_hm_device_health_tenant ON public.hypermesh_device_health USING btree (tenant_id);


--

-- INDEX: ix_hm_devices_tenant
CREATE INDEX ix_hm_devices_tenant ON public.hypermesh_devices USING btree (tenant_id);


--

-- INDEX: ix_hm_devices_tenant_site
CREATE INDEX ix_hm_devices_tenant_site ON public.hypermesh_devices USING btree (tenant_id, site_id);


--

-- INDEX: ix_hm_fleet_alerts_device
CREATE INDEX ix_hm_fleet_alerts_device ON public.hypermesh_fleet_alerts USING btree (device_id);


--

-- INDEX: ix_hm_fleet_alerts_tenant
CREATE INDEX ix_hm_fleet_alerts_tenant ON public.hypermesh_fleet_alerts USING btree (tenant_id);


--

-- INDEX: ix_hm_gateway_metrics_tenant
CREATE INDEX ix_hm_gateway_metrics_tenant ON public.hypermesh_gateway_metrics USING btree (tenant_id);


--

-- INDEX: ix_hm_gateways_tenant
CREATE INDEX ix_hm_gateways_tenant ON public.hypermesh_gateways USING btree (tenant_id);


--

-- INDEX: ix_hm_host_cert_overrides_tenant
CREATE INDEX ix_hm_host_cert_overrides_tenant ON public.hypermesh_host_cert_overrides USING btree (tenant_id);


--

-- INDEX: ix_hm_host_cert_overrides_tenant_device
CREATE INDEX ix_hm_host_cert_overrides_tenant_device ON public.hypermesh_host_cert_overrides USING btree (tenant_id, device_id);


--

-- INDEX: ix_hm_hw_classes_tenant
CREATE INDEX ix_hm_hw_classes_tenant ON public.hypermesh_hardware_classes USING btree (tenant_id);


--

-- INDEX: ix_hm_jobs_tenant
CREATE INDEX ix_hm_jobs_tenant ON public.hypermesh_jobs USING btree (tenant_id);


--

-- INDEX: ix_hm_lease_audit_tenant
CREATE INDEX ix_hm_lease_audit_tenant ON public.hypermesh_lease_audit USING btree (tenant_id);


--

-- INDEX: ix_hm_lease_audit_tenant_lease
CREATE INDEX ix_hm_lease_audit_tenant_lease ON public.hypermesh_lease_audit USING btree (tenant_id, lease_id);


--

-- INDEX: ix_hm_leases_tenant
CREATE INDEX ix_hm_leases_tenant ON public.hypermesh_leases USING btree (tenant_id);


--

-- INDEX: ix_hm_onboarding_device
CREATE INDEX ix_hm_onboarding_device ON public.hypermesh_onboarding_runs USING btree (tenant_id, device_id);


--

-- INDEX: ix_hm_payouts_tenant
CREATE INDEX ix_hm_payouts_tenant ON public.hypermesh_payouts USING btree (tenant_id);


--

-- INDEX: ix_hm_pool_prices_tenant
CREATE INDEX ix_hm_pool_prices_tenant ON public.hypermesh_pool_prices USING btree (tenant_id);


--

-- INDEX: ix_hm_pricing_alerts_tenant
CREATE INDEX ix_hm_pricing_alerts_tenant ON public.hypermesh_pricing_alerts USING btree (tenant_id);


--

-- INDEX: ix_hm_pricing_cost_class
CREATE INDEX ix_hm_pricing_cost_class ON public.hypermesh_cost_inputs USING btree (tenant_id, class_id, effective_from);


--

-- INDEX: ix_hm_pricing_cost_device
CREATE INDEX ix_hm_pricing_cost_device ON public.hypermesh_cost_inputs USING btree (device_id);


--

-- INDEX: ix_hm_pricing_cost_tenant
CREATE INDEX ix_hm_pricing_cost_tenant ON public.hypermesh_cost_inputs USING btree (tenant_id);


--

-- INDEX: ix_hm_pricing_fills_round
CREATE INDEX ix_hm_pricing_fills_round ON public.hypermesh_fills USING btree (round_id);


--

-- INDEX: ix_hm_pricing_fills_tenant
CREATE INDEX ix_hm_pricing_fills_tenant ON public.hypermesh_fills USING btree (tenant_id);


--

-- INDEX: ix_hm_pricing_orders_org
CREATE INDEX ix_hm_pricing_orders_org ON public.hypermesh_orders USING btree (tenant_id, org_id);


--

-- INDEX: ix_hm_pricing_orders_tenant
CREATE INDEX ix_hm_pricing_orders_tenant ON public.hypermesh_orders USING btree (tenant_id);


--

-- INDEX: ix_hm_pricing_pools_tenant
CREATE INDEX ix_hm_pricing_pools_tenant ON public.hypermesh_pricing_pools USING btree (tenant_id);


--

-- INDEX: ix_hm_pricing_rounds_start
CREATE INDEX ix_hm_pricing_rounds_start ON public.hypermesh_pricing_rounds USING btree (tenant_id, round_start);


--

-- INDEX: ix_hm_pricing_rounds_tenant
CREATE INDEX ix_hm_pricing_rounds_tenant ON public.hypermesh_pricing_rounds USING btree (tenant_id);


--

-- INDEX: ix_hm_privilege_grants_tenant
CREATE INDEX ix_hm_privilege_grants_tenant ON public.hypermesh_privilege_grants USING btree (tenant_id);


--

-- INDEX: ix_hm_privilege_grants_tenant_site
CREATE INDEX ix_hm_privilege_grants_tenant_site ON public.hypermesh_privilege_grants USING btree (tenant_id, site_id);


--

-- INDEX: ix_hm_privilege_grants_tenant_site_incident
CREATE INDEX ix_hm_privilege_grants_tenant_site_incident ON public.hypermesh_privilege_grants USING btree (tenant_id, site_id, incident_id);


--

-- INDEX: ix_hm_privilege_grants_tenant_site_status
CREATE INDEX ix_hm_privilege_grants_tenant_site_status ON public.hypermesh_privilege_grants USING btree (tenant_id, site_id, status);


--

-- INDEX: ix_hm_registration_outbox
CREATE INDEX ix_hm_registration_outbox ON public.hypermesh_host_registrations USING btree (tenant_id, created_at, id) WHERE ((enrollment_event IS NOT NULL) AND (event_forwarded_at IS NULL));


--

-- INDEX: ix_hm_registration_owner
CREATE INDEX ix_hm_registration_owner ON public.hypermesh_host_registrations USING btree (tenant_id, owner_sub);


--

-- INDEX: ix_hm_revoked_tickets_tenant
CREATE INDEX ix_hm_revoked_tickets_tenant ON public.hypermesh_revoked_tickets USING btree (tenant_id);


--

-- INDEX: ix_hm_scorecards_tenant
CREATE INDEX ix_hm_scorecards_tenant ON public.hypermesh_scorecards USING btree (tenant_id);


--

-- INDEX: ix_hm_site_tokens_tenant
CREATE INDEX ix_hm_site_tokens_tenant ON public.hypermesh_site_tokens USING btree (tenant_id);


--

-- INDEX: ix_hm_site_tokens_tenant_site
CREATE INDEX ix_hm_site_tokens_tenant_site ON public.hypermesh_site_tokens USING btree (tenant_id, site_id);


--

-- INDEX: ix_hm_tickets_tenant
CREATE INDEX ix_hm_tickets_tenant ON public.hypermesh_tickets USING btree (tenant_id);


--

-- INDEX: ix_hm_tunnels_tenant
CREATE INDEX ix_hm_tunnels_tenant ON public.hypermesh_tunnels USING btree (tenant_id);


--

-- INDEX: uq_hm_auditor_tickets_receipt
CREATE UNIQUE INDEX uq_hm_auditor_tickets_receipt ON public.hypermesh_auditor_tickets USING btree (tenant_id, site_id, receipt_id) WHERE (receipt_id IS NOT NULL);


--

-- INDEX: uq_hm_auditor_tickets_trace_reason
CREATE UNIQUE INDEX uq_hm_auditor_tickets_trace_reason ON public.hypermesh_auditor_tickets USING btree (tenant_id, site_id, trace_id, reason_code) WHERE (receipt_id IS NULL);


--

-- INDEX: uq_hm_devices_tenant_host_name
CREATE UNIQUE INDEX uq_hm_devices_tenant_host_name ON public.hypermesh_devices USING btree (tenant_id, host_name) WHERE ((archived_at IS NULL) AND enrolled AND (host_name IS NOT NULL));


--

-- INDEX: uq_hm_devices_tenant_serial
CREATE UNIQUE INDEX uq_hm_devices_tenant_serial ON public.hypermesh_devices USING btree (tenant_id, serial) WHERE (archived_at IS NULL);


--

-- INDEX: uq_hm_devices_wg_key
CREATE UNIQUE INDEX uq_hm_devices_wg_key ON public.hypermesh_devices USING btree (wg_public_key) WHERE (wg_public_key IS NOT NULL);


--

-- INDEX: uq_hm_fleet_alert_open
CREATE UNIQUE INDEX uq_hm_fleet_alert_open ON public.hypermesh_fleet_alerts USING btree (device_id, kind) WHERE ((state)::text = 'open'::text);


--

-- INDEX: uq_hm_pricing_alert_open_device
CREATE UNIQUE INDEX uq_hm_pricing_alert_open_device ON public.hypermesh_pricing_alerts USING btree (tenant_id, device_id, kind) WHERE (((state)::text = 'open'::text) AND (device_id IS NOT NULL));


--

-- INDEX: uq_hm_pricing_alert_open_pool
CREATE UNIQUE INDEX uq_hm_pricing_alert_open_pool ON public.hypermesh_pricing_alerts USING btree (tenant_id, pool_id, kind) WHERE (((state)::text = 'open'::text) AND (pool_id IS NOT NULL) AND (device_id IS NULL));


--

-- INDEX: uq_hm_privilege_grants_idem
CREATE UNIQUE INDEX uq_hm_privilege_grants_idem ON public.hypermesh_privilege_grants USING btree (tenant_id, site_id, idempotency_key) WHERE (idempotency_key IS NOT NULL);


--

-- INDEX: uq_hm_privilege_grants_natural
CREATE UNIQUE INDEX uq_hm_privilege_grants_natural ON public.hypermesh_privilege_grants USING btree (tenant_id, site_id, incident_id, trace_id);


--

-- INDEX: uq_hm_scorecard_content
CREATE UNIQUE INDEX uq_hm_scorecard_content ON public.hypermesh_scorecards USING btree (content_sha256) WHERE (content_sha256 IS NOT NULL);


--

-- INDEX: uq_hm_scorecard_source
CREATE UNIQUE INDEX uq_hm_scorecard_source ON public.hypermesh_scorecards USING btree (source_repo, source_commit, source_path) WHERE ((source_repo IS NOT NULL) AND (source_commit IS NOT NULL) AND (source_path IS NOT NULL));


--

-- FK CONSTRAINT: hypermesh_host_registrations fk_hm_registration_org_tenant
ALTER TABLE ONLY public.hypermesh_host_registrations
    ADD CONSTRAINT fk_hm_registration_org_tenant FOREIGN KEY (host_org_id, tenant_id) REFERENCES public.organizations(id, tenant_id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: host_organization_bindings fk_host_org_binding_organization_tenant
ALTER TABLE ONLY public.host_organization_bindings
    ADD CONSTRAINT fk_host_org_binding_organization_tenant FOREIGN KEY (organization_id, tenant_id) REFERENCES public.organizations(id, tenant_id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: host_organization_bindings host_organization_bindings_tenant_id_fkey
ALTER TABLE ONLY public.host_organization_bindings
    ADD CONSTRAINT host_organization_bindings_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_auditor_tickets hypermesh_auditor_tickets_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_auditor_tickets
    ADD CONSTRAINT hypermesh_auditor_tickets_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_catalog hypermesh_catalog_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_catalog
    ADD CONSTRAINT hypermesh_catalog_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_cost_inputs hypermesh_cost_inputs_device_id_fkey
ALTER TABLE ONLY public.hypermesh_cost_inputs
    ADD CONSTRAINT hypermesh_cost_inputs_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.hypermesh_devices(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_cost_inputs hypermesh_cost_inputs_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_cost_inputs
    ADD CONSTRAINT hypermesh_cost_inputs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_device_health hypermesh_device_health_device_id_fkey
ALTER TABLE ONLY public.hypermesh_device_health
    ADD CONSTRAINT hypermesh_device_health_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.hypermesh_devices(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_device_health hypermesh_device_health_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_device_health
    ADD CONSTRAINT hypermesh_device_health_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_devices hypermesh_devices_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_devices
    ADD CONSTRAINT hypermesh_devices_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_fills hypermesh_fills_device_id_fkey
ALTER TABLE ONLY public.hypermesh_fills
    ADD CONSTRAINT hypermesh_fills_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.hypermesh_devices(id) ON DELETE SET NULL;


--

-- FK CONSTRAINT: hypermesh_fills hypermesh_fills_lease_id_fkey
ALTER TABLE ONLY public.hypermesh_fills
    ADD CONSTRAINT hypermesh_fills_lease_id_fkey FOREIGN KEY (lease_id) REFERENCES public.hypermesh_leases(id) ON DELETE SET NULL;


--

-- FK CONSTRAINT: hypermesh_fills hypermesh_fills_order_id_fkey
ALTER TABLE ONLY public.hypermesh_fills
    ADD CONSTRAINT hypermesh_fills_order_id_fkey FOREIGN KEY (order_id) REFERENCES public.hypermesh_orders(order_id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_fills hypermesh_fills_pool_id_fkey
ALTER TABLE ONLY public.hypermesh_fills
    ADD CONSTRAINT hypermesh_fills_pool_id_fkey FOREIGN KEY (pool_id) REFERENCES public.hypermesh_pricing_pools(pool_id) ON DELETE RESTRICT;


--

-- FK CONSTRAINT: hypermesh_fills hypermesh_fills_round_id_fkey
ALTER TABLE ONLY public.hypermesh_fills
    ADD CONSTRAINT hypermesh_fills_round_id_fkey FOREIGN KEY (round_id) REFERENCES public.hypermesh_pricing_rounds(round_id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_fills hypermesh_fills_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_fills
    ADD CONSTRAINT hypermesh_fills_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_fleet_alerts hypermesh_fleet_alerts_device_id_fkey
ALTER TABLE ONLY public.hypermesh_fleet_alerts
    ADD CONSTRAINT hypermesh_fleet_alerts_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.hypermesh_devices(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_fleet_alerts hypermesh_fleet_alerts_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_fleet_alerts
    ADD CONSTRAINT hypermesh_fleet_alerts_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_fleet_health_config hypermesh_fleet_health_config_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_fleet_health_config
    ADD CONSTRAINT hypermesh_fleet_health_config_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_gateway_metrics hypermesh_gateway_metrics_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_gateway_metrics
    ADD CONSTRAINT hypermesh_gateway_metrics_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_gateways hypermesh_gateways_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_gateways
    ADD CONSTRAINT hypermesh_gateways_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_hardware_classes hypermesh_hardware_classes_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_hardware_classes
    ADD CONSTRAINT hypermesh_hardware_classes_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_host_cert_overrides hypermesh_host_cert_overrides_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_host_cert_overrides
    ADD CONSTRAINT hypermesh_host_cert_overrides_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_host_registrations hypermesh_host_registrations_device_id_fkey
ALTER TABLE ONLY public.hypermesh_host_registrations
    ADD CONSTRAINT hypermesh_host_registrations_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.hypermesh_devices(id);


--

-- FK CONSTRAINT: hypermesh_host_registrations hypermesh_host_registrations_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_host_registrations
    ADD CONSTRAINT hypermesh_host_registrations_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_jobs hypermesh_jobs_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_jobs
    ADD CONSTRAINT hypermesh_jobs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_lease_audit hypermesh_lease_audit_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_lease_audit
    ADD CONSTRAINT hypermesh_lease_audit_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_leases hypermesh_leases_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_leases
    ADD CONSTRAINT hypermesh_leases_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_onboarding_runs hypermesh_onboarding_runs_device_id_fkey
ALTER TABLE ONLY public.hypermesh_onboarding_runs
    ADD CONSTRAINT hypermesh_onboarding_runs_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.hypermesh_devices(id);


--

-- FK CONSTRAINT: hypermesh_onboarding_runs hypermesh_onboarding_runs_registration_id_fkey
ALTER TABLE ONLY public.hypermesh_onboarding_runs
    ADD CONSTRAINT hypermesh_onboarding_runs_registration_id_fkey FOREIGN KEY (registration_id) REFERENCES public.hypermesh_host_registrations(id);


--

-- FK CONSTRAINT: hypermesh_onboarding_runs hypermesh_onboarding_runs_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_onboarding_runs
    ADD CONSTRAINT hypermesh_onboarding_runs_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_orders hypermesh_orders_pool_id_fkey
ALTER TABLE ONLY public.hypermesh_orders
    ADD CONSTRAINT hypermesh_orders_pool_id_fkey FOREIGN KEY (pool_id) REFERENCES public.hypermesh_pricing_pools(pool_id) ON DELETE RESTRICT;


--

-- FK CONSTRAINT: hypermesh_orders hypermesh_orders_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_orders
    ADD CONSTRAINT hypermesh_orders_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_payouts hypermesh_payouts_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_payouts
    ADD CONSTRAINT hypermesh_payouts_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_pool_prices hypermesh_pool_prices_pool_id_fkey
ALTER TABLE ONLY public.hypermesh_pool_prices
    ADD CONSTRAINT hypermesh_pool_prices_pool_id_fkey FOREIGN KEY (pool_id) REFERENCES public.hypermesh_pricing_pools(pool_id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_pool_prices hypermesh_pool_prices_round_id_fkey
ALTER TABLE ONLY public.hypermesh_pool_prices
    ADD CONSTRAINT hypermesh_pool_prices_round_id_fkey FOREIGN KEY (round_id) REFERENCES public.hypermesh_pricing_rounds(round_id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_pool_prices hypermesh_pool_prices_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_pool_prices
    ADD CONSTRAINT hypermesh_pool_prices_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_pricing_alerts hypermesh_pricing_alerts_device_id_fkey
ALTER TABLE ONLY public.hypermesh_pricing_alerts
    ADD CONSTRAINT hypermesh_pricing_alerts_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.hypermesh_devices(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_pricing_alerts hypermesh_pricing_alerts_pool_id_fkey
ALTER TABLE ONLY public.hypermesh_pricing_alerts
    ADD CONSTRAINT hypermesh_pricing_alerts_pool_id_fkey FOREIGN KEY (pool_id) REFERENCES public.hypermesh_pricing_pools(pool_id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_pricing_alerts hypermesh_pricing_alerts_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_pricing_alerts
    ADD CONSTRAINT hypermesh_pricing_alerts_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_pricing_pools hypermesh_pricing_pools_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_pricing_pools
    ADD CONSTRAINT hypermesh_pricing_pools_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_pricing_rounds hypermesh_pricing_rounds_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_pricing_rounds
    ADD CONSTRAINT hypermesh_pricing_rounds_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_privilege_grants hypermesh_privilege_grants_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_privilege_grants
    ADD CONSTRAINT hypermesh_privilege_grants_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_revoked_tickets hypermesh_revoked_tickets_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_revoked_tickets
    ADD CONSTRAINT hypermesh_revoked_tickets_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_scorecards hypermesh_scorecards_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_scorecards
    ADD CONSTRAINT hypermesh_scorecards_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_site_tokens hypermesh_site_tokens_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_site_tokens
    ADD CONSTRAINT hypermesh_site_tokens_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_tickets hypermesh_tickets_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_tickets
    ADD CONSTRAINT hypermesh_tickets_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- FK CONSTRAINT: hypermesh_tunnels hypermesh_tunnels_tenant_id_fkey
ALTER TABLE ONLY public.hypermesh_tunnels
    ADD CONSTRAINT hypermesh_tunnels_tenant_id_fkey FOREIGN KEY (tenant_id) REFERENCES public.tenants(id) ON DELETE CASCADE;


--

-- ROW SECURITY: host_organization_bindings
ALTER TABLE public.host_organization_bindings ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_auditor_tickets
ALTER TABLE public.hypermesh_auditor_tickets ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_catalog
ALTER TABLE public.hypermesh_catalog ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_cost_inputs
ALTER TABLE public.hypermesh_cost_inputs ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_device_health
ALTER TABLE public.hypermesh_device_health ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_devices
ALTER TABLE public.hypermesh_devices ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_fills
ALTER TABLE public.hypermesh_fills ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_fleet_alerts
ALTER TABLE public.hypermesh_fleet_alerts ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_fleet_health_config
ALTER TABLE public.hypermesh_fleet_health_config ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_gateway_metrics
ALTER TABLE public.hypermesh_gateway_metrics ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_gateways
ALTER TABLE public.hypermesh_gateways ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_hardware_classes
ALTER TABLE public.hypermesh_hardware_classes ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_host_cert_overrides
ALTER TABLE public.hypermesh_host_cert_overrides ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_host_registrations
ALTER TABLE public.hypermesh_host_registrations ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_jobs
ALTER TABLE public.hypermesh_jobs ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_lease_audit
ALTER TABLE public.hypermesh_lease_audit ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_leases
ALTER TABLE public.hypermesh_leases ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_onboarding_runs
ALTER TABLE public.hypermesh_onboarding_runs ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_orders
ALTER TABLE public.hypermesh_orders ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_payouts
ALTER TABLE public.hypermesh_payouts ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_pool_prices
ALTER TABLE public.hypermesh_pool_prices ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_pricing_alerts
ALTER TABLE public.hypermesh_pricing_alerts ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_pricing_pools
ALTER TABLE public.hypermesh_pricing_pools ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_pricing_rounds
ALTER TABLE public.hypermesh_pricing_rounds ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_privilege_grants
ALTER TABLE public.hypermesh_privilege_grants ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_revoked_tickets
ALTER TABLE public.hypermesh_revoked_tickets ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_scorecards
ALTER TABLE public.hypermesh_scorecards ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_site_tokens
ALTER TABLE public.hypermesh_site_tokens ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_tickets
ALTER TABLE public.hypermesh_tickets ENABLE ROW LEVEL SECURITY;

--

-- ROW SECURITY: hypermesh_tunnels
ALTER TABLE public.hypermesh_tunnels ENABLE ROW LEVEL SECURITY;

--

-- POLICY: host_organization_bindings tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.host_organization_bindings FOR DELETE USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--

-- POLICY: hypermesh_auditor_tickets tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_auditor_tickets FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_catalog tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_catalog FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_cost_inputs tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_cost_inputs FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_device_health tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_device_health FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_devices tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_devices FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_fills tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_fills FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_fleet_alerts tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_fleet_alerts FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_fleet_health_config tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_fleet_health_config FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_gateway_metrics tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_gateway_metrics FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_gateways tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_gateways FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_hardware_classes tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_hardware_classes FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_host_cert_overrides tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_host_cert_overrides FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_host_registrations tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_host_registrations FOR DELETE USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--

-- POLICY: hypermesh_jobs tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_jobs FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_lease_audit tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_lease_audit FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_leases tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_leases FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_onboarding_runs tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_onboarding_runs FOR DELETE USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--

-- POLICY: hypermesh_orders tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_orders FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_payouts tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_payouts FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_pool_prices tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_pool_prices FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_pricing_alerts tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_pricing_alerts FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_pricing_pools tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_pricing_pools FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_pricing_rounds tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_pricing_rounds FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_privilege_grants tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_privilege_grants FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_revoked_tickets tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_revoked_tickets FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_scorecards tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_scorecards FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_site_tokens tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_site_tokens FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_tickets tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_tickets FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_tunnels tenant_isolation_delete
CREATE POLICY tenant_isolation_delete ON public.hypermesh_tunnels FOR DELETE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: host_organization_bindings tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.host_organization_bindings FOR INSERT WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--

-- POLICY: hypermesh_auditor_tickets tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_auditor_tickets FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_catalog tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_catalog FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_cost_inputs tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_cost_inputs FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_device_health tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_device_health FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_devices tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_devices FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_fills tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_fills FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_fleet_alerts tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_fleet_alerts FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_fleet_health_config tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_fleet_health_config FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_gateway_metrics tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_gateway_metrics FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_gateways tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_gateways FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_hardware_classes tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_hardware_classes FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_host_cert_overrides tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_host_cert_overrides FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_host_registrations tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_host_registrations FOR INSERT WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--

-- POLICY: hypermesh_jobs tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_jobs FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_lease_audit tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_lease_audit FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_leases tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_leases FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_onboarding_runs tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_onboarding_runs FOR INSERT WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--

-- POLICY: hypermesh_orders tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_orders FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_payouts tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_payouts FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_pool_prices tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_pool_prices FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_pricing_alerts tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_pricing_alerts FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_pricing_pools tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_pricing_pools FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_pricing_rounds tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_pricing_rounds FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_privilege_grants tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_privilege_grants FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_revoked_tickets tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_revoked_tickets FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_scorecards tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_scorecards FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_site_tokens tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_site_tokens FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_tickets tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_tickets FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_tunnels tenant_isolation_insert
CREATE POLICY tenant_isolation_insert ON public.hypermesh_tunnels FOR INSERT WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: host_organization_bindings tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.host_organization_bindings FOR SELECT USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--

-- POLICY: hypermesh_auditor_tickets tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_auditor_tickets FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_catalog tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_catalog FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_cost_inputs tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_cost_inputs FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_device_health tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_device_health FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_devices tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_devices FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_fills tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_fills FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_fleet_alerts tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_fleet_alerts FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_fleet_health_config tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_fleet_health_config FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_gateway_metrics tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_gateway_metrics FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_gateways tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_gateways FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_hardware_classes tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_hardware_classes FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_host_cert_overrides tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_host_cert_overrides FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_host_registrations tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_host_registrations FOR SELECT USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--

-- POLICY: hypermesh_jobs tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_jobs FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_lease_audit tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_lease_audit FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_leases tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_leases FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_onboarding_runs tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_onboarding_runs FOR SELECT USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--

-- POLICY: hypermesh_orders tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_orders FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_payouts tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_payouts FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_pool_prices tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_pool_prices FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_pricing_alerts tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_pricing_alerts FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_pricing_pools tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_pricing_pools FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_pricing_rounds tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_pricing_rounds FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_privilege_grants tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_privilege_grants FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_revoked_tickets tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_revoked_tickets FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_scorecards tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_scorecards FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_site_tokens tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_site_tokens FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_tickets tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_tickets FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_tunnels tenant_isolation_select
CREATE POLICY tenant_isolation_select ON public.hypermesh_tunnels FOR SELECT USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: host_organization_bindings tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.host_organization_bindings FOR UPDATE USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--

-- POLICY: hypermesh_auditor_tickets tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_auditor_tickets FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_catalog tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_catalog FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_cost_inputs tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_cost_inputs FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_device_health tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_device_health FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_devices tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_devices FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_fills tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_fills FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_fleet_alerts tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_fleet_alerts FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_fleet_health_config tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_fleet_health_config FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_gateway_metrics tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_gateway_metrics FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_gateways tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_gateways FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_hardware_classes tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_hardware_classes FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_host_cert_overrides tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_host_cert_overrides FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_host_registrations tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_host_registrations FOR UPDATE USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--

-- POLICY: hypermesh_jobs tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_jobs FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_lease_audit tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_lease_audit FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_leases tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_leases FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_onboarding_runs tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_onboarding_runs FOR UPDATE USING ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid)) WITH CHECK ((tenant_id = (NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid));


--

-- POLICY: hypermesh_orders tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_orders FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_payouts tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_payouts FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_pool_prices tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_pool_prices FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_pricing_alerts tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_pricing_alerts FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_pricing_pools tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_pricing_pools FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_pricing_rounds tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_pricing_rounds FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_privilege_grants tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_privilege_grants FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_revoked_tickets tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_revoked_tickets FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_scorecards tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_scorecards FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_site_tokens tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_site_tokens FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_tickets tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_tickets FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--

-- POLICY: hypermesh_tunnels tenant_isolation_update
CREATE POLICY tenant_isolation_update ON public.hypermesh_tunnels FOR UPDATE USING ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid)))) WITH CHECK ((((current_setting('app.current_tenant_id'::text, true) = ''::text) AND (tenant_id IS NULL)) OR ((current_setting('app.current_tenant_id'::text, true) <> ''::text) AND (tenant_id IS NOT NULL) AND (tenant_id = (current_setting('app.current_tenant_id'::text, true))::uuid))));


--
