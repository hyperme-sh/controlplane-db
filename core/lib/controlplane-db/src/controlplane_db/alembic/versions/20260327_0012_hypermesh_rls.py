"""Hypermesh control-plane tables (tenant_id + RLS).

Revision ID: 0012_hypermesh
Revises: 0011_api_keys
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012_hypermesh"
down_revision = "0011_api_keys"
branch_labels = None
depends_on = None

_MARKETPLACE_TENANT = "8f8e8d8c-7b6a-4a59-8c3d-2e1f0a9b8c7d"

_TABLES = (
    "hypermesh_hardware_classes",
    "hypermesh_devices",
    "hypermesh_catalog",
    "hypermesh_leases",
    "hypermesh_jobs",
    "hypermesh_tunnels",
    "hypermesh_payouts",
    "hypermesh_routers",
    "hypermesh_router_metrics",
    "hypermesh_tickets",
    "hypermesh_revoked_tickets",
)


def _tenant_policy_sql(table: str, op_name: str) -> str:
    cond = """(
                (current_setting('app.current_tenant_id', true) = '' AND tenant_id IS NULL)
                OR (
                    current_setting('app.current_tenant_id', true) <> ''
                    AND tenant_id IS NOT NULL
                    AND tenant_id = current_setting('app.current_tenant_id', true)::uuid
                )
            )"""
    if op_name == "select":
        return f"""
            CREATE POLICY tenant_isolation_select ON "{table}"
            FOR SELECT
            USING {cond}
            """
    if op_name == "insert":
        return f"""
            CREATE POLICY tenant_isolation_insert ON "{table}"
            FOR INSERT
            WITH CHECK {cond}
            """
    if op_name == "update":
        return f"""
            CREATE POLICY tenant_isolation_update ON "{table}"
            FOR UPDATE
            USING {cond}
            WITH CHECK {cond}
            """
    return f"""
        CREATE POLICY tenant_isolation_delete ON "{table}"
        FOR DELETE
        USING {cond}
        """


def _enable_rls(table: str) -> None:
    op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))
    op.execute(sa.text(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY'))
    for pol in (
        "tenant_isolation_select",
        "tenant_isolation_insert",
        "tenant_isolation_update",
        "tenant_isolation_delete",
    ):
        op.execute(sa.text(f'DROP POLICY IF EXISTS {pol} ON "{table}"'))
    for kind in ("select", "insert", "update", "delete"):
        op.execute(sa.text(_tenant_policy_sql(table, kind)))


def upgrade() -> None:
    op.execute(
        sa.text(
            f"""
            INSERT INTO tenants (id, name, is_active)
            VALUES ('{_MARKETPLACE_TENANT}', 'Hypermesh marketplace', true)
            ON CONFLICT (id) DO NOTHING
            """
        )
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS hypermesh_hardware_classes (
                id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                class_id VARCHAR(64) NOT NULL,
                vendor VARCHAR(64) NOT NULL,
                sku VARCHAR(128) NOT NULL,
                module VARCHAR(64) NOT NULL,
                memory_gb INTEGER NOT NULL,
                public_sku BOOLEAN NOT NULL DEFAULT true,
                path_b_suite_id VARCHAR(64) NOT NULL,
                hourly_rate_cents INTEGER NOT NULL,
                advertised_envelope TEXT,
                UNIQUE (tenant_id, class_id)
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_hm_hw_classes_tenant "
            "ON hypermesh_hardware_classes (tenant_id)"
        )
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS hypermesh_devices (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                class_id VARCHAR(64) NOT NULL,
                host_org_id UUID NOT NULL,
                serial VARCHAR(128) NOT NULL,
                path_a JSONB NOT NULL,
                path_b_state VARCHAR(32) NOT NULL,
                loaded_instance_state VARCHAR(32) NOT NULL,
                loaded_catalog_id VARCHAR(64),
                enroll_token_hash VARCHAR(64),
                enroll_token_used_hash VARCHAR(64),
                enroll_token_prefix VARCHAR(16),
                device_secret_hash VARCHAR(64),
                credential_prefix VARCHAR(16),
                enrolled BOOLEAN NOT NULL DEFAULT false,
                last_heartbeat_at TIMESTAMPTZ,
                last_path_b_at TIMESTAMPTZ,
                last_image_hash VARCHAR(128),
                last_loaded_model_hash VARCHAR(128),
                last_uptime_s INTEGER,
                last_thermal_c DOUBLE PRECISION,
                usdc_pubkey VARCHAR(64),
                created_at TIMESTAMPTZ NOT NULL,
                UNIQUE (tenant_id, serial)
            )
            """
        )
    )
    op.execute(
        sa.text("CREATE INDEX IF NOT EXISTS ix_hm_devices_tenant ON hypermesh_devices (tenant_id)")
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS hypermesh_catalog (
                id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                catalog_id VARCHAR(64) NOT NULL,
                artifact_name VARCHAR(256) NOT NULL,
                class_id VARCHAR(64) NOT NULL,
                file_hash VARCHAR(256),
                quant VARCHAR(32),
                format VARCHAR(32),
                runtime VARCHAR(64),
                advertised_context INTEGER,
                certified BOOLEAN NOT NULL DEFAULT false,
                per_1k_token_cents INTEGER NOT NULL,
                loaded_hour_min_cents INTEGER NOT NULL,
                UNIQUE (tenant_id, catalog_id)
            )
            """
        )
    )
    op.execute(
        sa.text("CREATE INDEX IF NOT EXISTS ix_hm_catalog_tenant ON hypermesh_catalog (tenant_id)")
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS hypermesh_leases (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                kind VARCHAR(32) NOT NULL,
                status VARCHAR(32) NOT NULL,
                renter_user_id UUID NOT NULL,
                class_id VARCHAR(64) NOT NULL,
                catalog_id VARCHAR(64),
                device_id UUID,
                host_org_id UUID,
                reserved_hours INTEGER NOT NULL,
                billing_record_id UUID,
                stripe_session_id VARCHAR(255),
                checkout_url TEXT,
                gross_cents INTEGER,
                token_count INTEGER NOT NULL DEFAULT 0,
                loaded_hours INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL,
                activated_at TIMESTAMPTZ,
                ended_at TIMESTAMPTZ
            )
            """
        )
    )
    op.execute(
        sa.text("CREATE INDEX IF NOT EXISTS ix_hm_leases_tenant ON hypermesh_leases (tenant_id)")
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS hypermesh_jobs (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                device_id UUID NOT NULL,
                suite_id VARCHAR(64),
                kind VARCHAR(32) NOT NULL,
                status VARCHAR(32) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                completed_at TIMESTAMPTZ,
                image_hash VARCHAR(256),
                lease_id UUID,
                catalog_id VARCHAR(64),
                image_digest VARCHAR(256),
                runtime VARCHAR(64),
                ticket TEXT
            )
            """
        )
    )
    op.execute(
        sa.text("CREATE INDEX IF NOT EXISTS ix_hm_jobs_tenant ON hypermesh_jobs (tenant_id)")
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS hypermesh_tunnels (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                lease_id UUID NOT NULL,
                device_id UUID NOT NULL,
                assigned_router_id UUID,
                status VARCHAR(32) NOT NULL,
                endpoint VARCHAR(256) NOT NULL,
                server_public_key VARCHAR(128) NOT NULL,
                server_private_key VARCHAR(128),
                peer_public_key VARCHAR(128),
                peer_private_key VARCHAR(128),
                allowed_ips VARCHAR(64) NOT NULL,
                client_address VARCHAR(64) NOT NULL,
                ack_applied BOOLEAN NOT NULL DEFAULT false,
                created_at TIMESTAMPTZ NOT NULL,
                expires_at TIMESTAMPTZ
            )
            """
        )
    )
    op.execute(
        sa.text("CREATE INDEX IF NOT EXISTS ix_hm_tunnels_tenant ON hypermesh_tunnels (tenant_id)")
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS hypermesh_payouts (
                lease_id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                host_org_id UUID NOT NULL,
                host_pubkey VARCHAR(128) NOT NULL,
                kind VARCHAR(32) NOT NULL,
                gross_cents INTEGER NOT NULL,
                stripe_cut_cents INTEGER NOT NULL,
                platform_take_cents INTEGER NOT NULL,
                take_bps INTEGER NOT NULL,
                net_cents INTEGER NOT NULL,
                net_usdc_atoms BIGINT NOT NULL
            )
            """
        )
    )
    op.execute(
        sa.text("CREATE INDEX IF NOT EXISTS ix_hm_payouts_tenant ON hypermesh_payouts (tenant_id)")
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS hypermesh_routers (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                name VARCHAR(128) NOT NULL,
                secret_hash VARCHAR(64),
                credential_prefix VARCHAR(16),
                created_at TIMESTAMPTZ NOT NULL,
                UNIQUE (tenant_id, name)
            )
            """
        )
    )
    op.execute(
        sa.text("CREATE INDEX IF NOT EXISTS ix_hm_routers_tenant ON hypermesh_routers (tenant_id)")
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS hypermesh_router_metrics (
                id UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                router_id UUID NOT NULL,
                tunnel_id UUID,
                lease_id UUID,
                bytes_in BIGINT NOT NULL DEFAULT 0,
                bytes_out BIGINT NOT NULL DEFAULT 0,
                handshake_count INTEGER NOT NULL DEFAULT 0,
                recorded_at TIMESTAMPTZ NOT NULL
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_hm_router_metrics_tenant "
            "ON hypermesh_router_metrics (tenant_id)"
        )
    )

    op.execute(sa.text("ALTER TABLE hypermesh_jobs ADD COLUMN IF NOT EXISTS ticket TEXT"))

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS hypermesh_tickets (
                lease_id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                device_id UUID NOT NULL,
                assigned_router_id UUID NOT NULL,
                client_address VARCHAR(64) NOT NULL,
                status VARCHAR(32) NOT NULL,
                exp TIMESTAMPTZ NOT NULL,
                ticket TEXT NOT NULL
            )
            """
        )
    )
    op.execute(
        sa.text("CREATE INDEX IF NOT EXISTS ix_hm_tickets_tenant ON hypermesh_tickets (tenant_id)")
    )

    op.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS hypermesh_revoked_tickets (
                lease_id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS ix_hm_revoked_tickets_tenant "
            "ON hypermesh_revoked_tickets (tenant_id)"
        )
    )

    for t in _TABLES:
        _enable_rls(t)


def downgrade() -> None:
    for table in reversed(_TABLES):
        for pol in (
            "tenant_isolation_select",
            "tenant_isolation_insert",
            "tenant_isolation_update",
            "tenant_isolation_delete",
        ):
            op.execute(sa.text(f'DROP POLICY IF EXISTS {pol} ON "{table}"'))
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{table}"'))
