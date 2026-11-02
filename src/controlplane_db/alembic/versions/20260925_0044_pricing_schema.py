"""Hypermesh pricing engine tables.

Revision ID: 0044_pricing_schema
Revises: 0043_device_host_type

Schema and persistence for FyberLabs/hypermesh-pricing. No scheduler and
no HTTP client. Pool id is ``<class_id>@<region>`` (region ``default`` until
a second region exists). ``pay_cents`` on a fill is per box-hour;
``total_cents`` is the slice. ``lottery_seed`` stays null until the round
reveals the seed whose sha256 was published in ``lottery_seed_commit``.

``ruleset_version`` and ``engine_version`` are NOT NULL on rounds and fills.
Leases gain a nullable ``ruleset_version`` so a receipt can name the ruleset
without backfilling old rows.

Pricing alerts are not fleet alerts. ``hypermesh_fleet_alerts.device_id`` is
NOT NULL, the open unique index is ``(device_id, kind)``, and the kind check
is heartbeat, handshake, tunnel sync, and build drift. A degraded-round
alert is per pool and often has no device. A null ``device_id`` would not
conflict in that unique index, so pool-level alerts live in
``hypermesh_pricing_alerts``.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0044_pricing_schema"
down_revision = "0043_device_host_type"
branch_labels = None
depends_on = None

_POOLS = "hypermesh_pricing_pools"
_ROUNDS = "hypermesh_pricing_rounds"
_PRICES = "hypermesh_pool_prices"
_ORDERS = "hypermesh_orders"
_FILLS = "hypermesh_fills"
_COSTS = "hypermesh_cost_inputs"
_ALERTS = "hypermesh_pricing_alerts"
_LEASES = "hypermesh_leases"


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
            CREATE TABLE IF NOT EXISTS {_POOLS} (
                pool_id VARCHAR(129) NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                class_id VARCHAR(64) NOT NULL,
                region VARCHAR(64) NOT NULL DEFAULT 'default',
                kind VARCHAR(2) NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                CONSTRAINT ck_hm_pricing_pool_kind CHECK (kind IN ('P1', 'P2')),
                CONSTRAINT ck_hm_pricing_pool_id_shape CHECK (
                    pool_id = class_id || '@' || region
                )
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_hm_pricing_pools_tenant ON {_POOLS} (tenant_id)"
        )
    )

    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS {_ROUNDS} (
                round_id VARCHAR(128) NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                round_start TIMESTAMPTZ NOT NULL,
                round_type VARCHAR(16) NOT NULL,
                ruleset_version VARCHAR(64) NOT NULL,
                engine_version VARCHAR(32) NOT NULL,
                degraded BOOLEAN NOT NULL,
                request_hash VARCHAR(64) NOT NULL,
                idempotency_key VARCHAR(128) NOT NULL,
                lottery_seed_commit VARCHAR(64) NOT NULL,
                lottery_seed VARCHAR(128),
                created_at TIMESTAMPTZ NOT NULL,
                CONSTRAINT ck_hm_pricing_round_type CHECK (
                    round_type IN ('realtime', 'day_ahead')
                ),
                CONSTRAINT ck_hm_pricing_round_ruleset CHECK (
                    char_length(ruleset_version) > 0
                ),
                CONSTRAINT ck_hm_pricing_round_engine CHECK (
                    char_length(engine_version) > 0
                ),
                CONSTRAINT ck_hm_pricing_round_request_hash CHECK (
                    request_hash ~ '^[0-9a-f]{{64}}$'
                ),
                CONSTRAINT ck_hm_pricing_round_seed_commit CHECK (
                    lottery_seed_commit ~ '^[0-9a-f]{{64}}$'
                ),
                CONSTRAINT ck_hm_pricing_round_seed CHECK (
                    lottery_seed IS NULL OR lottery_seed ~ '^[0-9a-f]{{1,128}}$'
                ),
                CONSTRAINT uq_hm_pricing_round_idempotency
                    UNIQUE (tenant_id, idempotency_key)
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_hm_pricing_rounds_tenant ON {_ROUNDS} (tenant_id)"
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS ix_hm_pricing_rounds_start
            ON {_ROUNDS} (tenant_id, round_start)
            """
        )
    )

    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS {_PRICES} (
                round_id VARCHAR(128) NOT NULL
                    REFERENCES {_ROUNDS}(round_id) ON DELETE CASCADE,
                pool_id VARCHAR(129) NOT NULL
                    REFERENCES {_POOLS}(pool_id) ON DELETE CASCADE,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                base_cents INTEGER NOT NULL,
                next_base_cents INTEGER NOT NULL,
                floor_cents INTEGER,
                reserve_cents INTEGER NOT NULL,
                cap_cents INTEGER NOT NULL,
                utilization NUMERIC NOT NULL,
                demand_hours NUMERIC NOT NULL,
                supply_hours NUMERIC NOT NULL,
                supply_clamped BOOLEAN NOT NULL,
                reserve_source VARCHAR(64) NOT NULL,
                rationed BOOLEAN NOT NULL,
                boost_active BOOLEAN NOT NULL,
                boost_multiple NUMERIC NOT NULL,
                at_cap BOOLEAN NOT NULL,
                at_floor BOOLEAN NOT NULL,
                scarce BOOLEAN NOT NULL,
                org_cap_applied BOOLEAN NOT NULL,
                degraded BOOLEAN NOT NULL,
                ruleset_version VARCHAR(64) NOT NULL,
                boost JSONB NOT NULL,
                next_ema_cents INTEGER NOT NULL,
                trailing_state JSONB NOT NULL,
                supply_tiers JSONB,
                PRIMARY KEY (round_id, pool_id),
                CONSTRAINT ck_hm_pool_price_cents CHECK (
                    base_cents >= 0 AND next_base_cents >= 0 AND reserve_cents >= 0
                    AND cap_cents >= 0 AND next_ema_cents >= 0
                    AND (floor_cents IS NULL OR floor_cents >= 0)
                ),
                CONSTRAINT ck_hm_pool_price_ruleset CHECK (
                    char_length(ruleset_version) > 0
                )
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_hm_pool_prices_tenant ON {_PRICES} (tenant_id)"
        )
    )

    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS {_ORDERS} (
                order_id VARCHAR(128) NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                org_id VARCHAR(128) NOT NULL,
                pool_id VARCHAR(129) NOT NULL
                    REFERENCES {_POOLS}(pool_id) ON DELETE RESTRICT,
                rungs JSONB NOT NULL,
                tip_cents INTEGER NOT NULL DEFAULT 0,
                hours NUMERIC NOT NULL,
                pain JSONB,
                status VARCHAR(16) NOT NULL,
                prepay_ref VARCHAR(255),
                created_at TIMESTAMPTZ NOT NULL,
                CONSTRAINT ck_hm_pricing_order_status CHECK (
                    status IN ('open', 'filled', 'partial', 'unfilled', 'cancelled')
                ),
                CONSTRAINT ck_hm_pricing_order_money CHECK (
                    tip_cents >= 0 AND hours > 0
                )
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_hm_pricing_orders_tenant ON {_ORDERS} (tenant_id)"
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS ix_hm_pricing_orders_org
            ON {_ORDERS} (tenant_id, org_id)
            """
        )
    )

    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS {_FILLS} (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                round_id VARCHAR(128) NOT NULL
                    REFERENCES {_ROUNDS}(round_id) ON DELETE CASCADE,
                order_id VARCHAR(128) NOT NULL
                    REFERENCES {_ORDERS}(order_id) ON DELETE CASCADE,
                pool_id VARCHAR(129) NOT NULL
                    REFERENCES {_POOLS}(pool_id) ON DELETE RESTRICT,
                org_id VARCHAR(128) NOT NULL,
                rung_index INTEGER NOT NULL,
                hours NUMERIC NOT NULL,
                device_id UUID REFERENCES hypermesh_devices(id) ON DELETE SET NULL,
                lease_id UUID REFERENCES hypermesh_leases(id) ON DELETE SET NULL,
                pay_cents INTEGER NOT NULL,
                total_cents INTEGER NOT NULL,
                tip_cents INTEGER NOT NULL,
                lock_until TIMESTAMPTZ NOT NULL,
                ruleset_version VARCHAR(64) NOT NULL,
                engine_version VARCHAR(32) NOT NULL,
                CONSTRAINT ck_hm_pricing_fill_money CHECK (
                    pay_cents >= 0 AND total_cents >= 0 AND tip_cents >= 0 AND hours > 0
                ),
                CONSTRAINT ck_hm_pricing_fill_versions CHECK (
                    char_length(ruleset_version) > 0
                    AND char_length(engine_version) > 0
                ),
                CONSTRAINT uq_hm_pricing_fill_natural
                    UNIQUE (round_id, order_id, pool_id, rung_index)
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_hm_pricing_fills_tenant ON {_FILLS} (tenant_id)"
        )
    )
    op.execute(
        sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_hm_pricing_fills_round ON {_FILLS} (round_id)"
        )
    )

    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS {_COSTS} (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                device_id UUID REFERENCES hypermesh_devices(id) ON DELETE CASCADE,
                class_id VARCHAR(64),
                capex_cents INTEGER NOT NULL,
                loaded_kw NUMERIC NOT NULL,
                tariff_cents_per_kwh INTEGER NOT NULL,
                overhead NUMERIC NOT NULL,
                residual NUMERIC NOT NULL,
                host_margin NUMERIC NOT NULL,
                processor_pct NUMERIC,
                processor_fixed_cents INTEGER,
                expected_hours_per_txn NUMERIC,
                source VARCHAR(64) NOT NULL,
                effective_from TIMESTAMPTZ NOT NULL,
                CONSTRAINT ck_hm_pricing_cost_scope CHECK (
                    (device_id IS NOT NULL AND class_id IS NULL)
                    OR (device_id IS NULL AND class_id IS NOT NULL)
                ),
                CONSTRAINT ck_hm_pricing_cost_nonneg CHECK (
                    capex_cents >= 0 AND tariff_cents_per_kwh >= 0 AND loaded_kw >= 0
                ),
                CONSTRAINT ck_hm_pricing_cost_processor CHECK (
                    processor_fixed_cents IS NULL OR processor_fixed_cents >= 0
                )
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_hm_pricing_cost_tenant ON {_COSTS} (tenant_id)"
        )
    )
    op.execute(
        sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_hm_pricing_cost_device ON {_COSTS} (device_id)"
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE INDEX IF NOT EXISTS ix_hm_pricing_cost_class
            ON {_COSTS} (tenant_id, class_id, effective_from)
            """
        )
    )

    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS {_ALERTS} (
                id UUID NOT NULL PRIMARY KEY,
                tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
                pool_id VARCHAR(129) REFERENCES {_POOLS}(pool_id) ON DELETE CASCADE,
                device_id UUID REFERENCES hypermesh_devices(id) ON DELETE CASCADE,
                kind VARCHAR(32) NOT NULL,
                state VARCHAR(16) NOT NULL,
                first_seen TIMESTAMPTZ NOT NULL,
                last_seen TIMESTAMPTZ NOT NULL,
                resolved_at TIMESTAMPTZ,
                detail VARCHAR(256),
                CONSTRAINT ck_hm_pricing_alert_kind CHECK (
                    kind IN ('degraded_rounds', 'engine_unreachable')
                ),
                CONSTRAINT ck_hm_pricing_alert_state CHECK (
                    state IN ('open', 'resolved')
                ),
                CONSTRAINT ck_hm_pricing_alert_scope CHECK (
                    pool_id IS NOT NULL OR device_id IS NOT NULL
                )
            )
            """
        )
    )
    op.execute(
        sa.text(
            f"CREATE INDEX IF NOT EXISTS ix_hm_pricing_alerts_tenant ON {_ALERTS} (tenant_id)"
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_hm_pricing_alert_open_pool
            ON {_ALERTS} (tenant_id, pool_id, kind)
            WHERE state = 'open' AND pool_id IS NOT NULL AND device_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_hm_pricing_alert_open_device
            ON {_ALERTS} (tenant_id, device_id, kind)
            WHERE state = 'open' AND device_id IS NOT NULL
            """
        )
    )

    op.execute(
        sa.text(
            f"""
            ALTER TABLE {_LEASES}
            ADD COLUMN IF NOT EXISTS ruleset_version VARCHAR(64)
            """
        )
    )

    for table in (_POOLS, _ROUNDS, _PRICES, _ORDERS, _FILLS, _COSTS, _ALERTS):
        _enable_rls(table)


def downgrade() -> None:
    for table in (_ALERTS, _FILLS, _ORDERS, _PRICES, _COSTS, _ROUNDS, _POOLS):
        op.execute(sa.text(f'DROP TABLE IF EXISTS "{table}"'))
    op.execute(sa.text(f"ALTER TABLE {_LEASES} DROP COLUMN IF EXISTS ruleset_version"))
