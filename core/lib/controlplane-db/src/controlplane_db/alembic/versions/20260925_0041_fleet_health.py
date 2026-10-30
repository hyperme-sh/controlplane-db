"""Fleet device health, alert state, and DB thresholds.

Revision ID: 0041_fleet_health
Revises: 0040_scorecard_host_version

Health is one row per device, written by that device's heartbeat.
Alert rows open once and resolve when the condition clears.
Thresholds and expected_build_commit live in the config table.
They are not environment variables. expected_build_commit stays
null until the deploy path sets it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0041_fleet_health"
down_revision = "0040_scorecard_host_version"
branch_labels = None
depends_on = None

_MARKETPLACE_TENANT = "8f8e8d8c-7b6a-4a59-8c3d-2e1f0a9b8c7d"
_HEALTH = "hypermesh_device_health"
_ALERTS = "hypermesh_fleet_alerts"
_CONFIG = "hypermesh_fleet_health_config"


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
            CREATE TABLE IF NOT EXISTS {_HEALTH} (
                device_id UUID NOT NULL PRIMARY KEY
                    REFERENCES hypermesh_devices(id) ON DELETE CASCADE,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                tunnel_state VARCHAR(32),
                last_sync_at TIMESTAMPTZ,
                last_sync_error_class VARCHAR(64),
                last_sync_http_status INTEGER,
                handshake_age_s INTEGER,
                wg_pid INTEGER,
                wg_port INTEGER,
                lease_container_count INTEGER,
                build_commit VARCHAR(64),
                received_at TIMESTAMPTZ NOT NULL,
                sync_error_since TIMESTAMPTZ,
                CONSTRAINT ck_hm_health_http_status CHECK (
                    last_sync_http_status IS NULL
                    OR (last_sync_http_status >= 0 AND last_sync_http_status <= 599)
                ),
                CONSTRAINT ck_hm_health_handshake CHECK (
                    handshake_age_s IS NULL OR handshake_age_s >= 0
                ),
                CONSTRAINT ck_hm_health_wg_pid CHECK (
                    wg_pid IS NULL OR wg_pid >= 0
                ),
                CONSTRAINT ck_hm_health_wg_port CHECK (
                    wg_port IS NULL OR (wg_port >= 1 AND wg_port <= 65535)
                ),
                CONSTRAINT ck_hm_health_containers CHECK (
                    lease_container_count IS NULL OR lease_container_count >= 0
                ),
                CONSTRAINT ck_hm_health_build_commit CHECK (
                    build_commit IS NULL
                    OR build_commit ~ '^[0-9a-f]{{1,64}}$'
                )
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_hm_device_health_tenant ON {_HEALTH} (tenant_id)"
        )
    )

    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS {_ALERTS} (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                device_id UUID NOT NULL
                    REFERENCES hypermesh_devices(id) ON DELETE CASCADE,
                kind VARCHAR(32) NOT NULL,
                state VARCHAR(16) NOT NULL,
                first_seen TIMESTAMPTZ NOT NULL,
                last_seen TIMESTAMPTZ NOT NULL,
                resolved_at TIMESTAMPTZ,
                detail VARCHAR(256),
                CONSTRAINT ck_hm_fleet_alert_kind CHECK (
                    kind IN (
                        'heartbeat_stale',
                        'handshake_stale',
                        'tunnel_sync_failing',
                        'build_drift'
                    )
                ),
                CONSTRAINT ck_hm_fleet_alert_state CHECK (
                    state IN ('open', 'resolved')
                )
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_hm_fleet_alerts_tenant ON {_ALERTS} (tenant_id)"
        )
    )
    op.execute(
        sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_hm_fleet_alerts_device ON {_ALERTS} (device_id)"
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_hm_fleet_alert_open
            ON {_ALERTS} (device_id, kind)
            WHERE state = 'open'
            """
        )
    )

    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS {_CONFIG} (
                tenant_id UUID NOT NULL PRIMARY KEY
                    REFERENCES tenants(id) ON DELETE CASCADE,
                heartbeat_stale_s INTEGER NOT NULL DEFAULT 180,
                handshake_stale_s INTEGER NOT NULL DEFAULT 300,
                sync_fail_s INTEGER NOT NULL DEFAULT 300,
                expected_build_commit VARCHAR(64),
                CONSTRAINT ck_hm_fleet_cfg_heartbeat CHECK (heartbeat_stale_s >= 1),
                CONSTRAINT ck_hm_fleet_cfg_handshake CHECK (handshake_stale_s >= 1),
                CONSTRAINT ck_hm_fleet_cfg_sync CHECK (sync_fail_s >= 1),
                CONSTRAINT ck_hm_fleet_cfg_commit CHECK (
                    expected_build_commit IS NULL
                    OR expected_build_commit ~ '^[0-9a-f]{{1,64}}$'
                )
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            INSERT INTO {_CONFIG} (
                tenant_id, heartbeat_stale_s, handshake_stale_s, sync_fail_s,
                expected_build_commit
            )
            VALUES ('{_MARKETPLACE_TENANT}', 180, 300, 300, NULL)
            ON CONFLICT (tenant_id) DO NOTHING
            """
        )
    )

    for table in (_HEALTH, _ALERTS, _CONFIG):
        _enable_rls(table)


def downgrade() -> None:
    for table in (_ALERTS, _HEALTH, _CONFIG):
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{table}"'))
