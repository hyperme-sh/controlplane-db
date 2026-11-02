"""Rename the router-era hypermesh schema to gateway.

Revision ID: 0023_gateway_rename
Revises: 0022_host_cert_override

Only databases created before the rename need this. 0012 builds the hypermesh
tables and now spells them ``hypermesh_gateways``, so a database created from an
empty schema arrives with the new names and every step below is a no-op. A
database that ran 0012 while it still said ``hypermesh_routers`` keeps the old
names, and nothing else in the chain would ever move them: that is how test
ended up serving ``column hypermesh_tunnels.assigned_gateway_id does not exist``
on every hypermesh boot.

Each step is guarded rather than wrapped in a version check, because the two
shapes are not the only two possibilities -- a database can be half-renamed if
an earlier attempt failed partway. Guarding per object makes re-running safe.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0023_gateway_rename"
down_revision = "0022_host_cert_override"
branch_labels = None
depends_on = None

_TABLES = (
    ("hypermesh_routers", "hypermesh_gateways"),
    ("hypermesh_router_metrics", "hypermesh_gateway_metrics"),
)

# Column renames, as (table, old, new). The table names here are the post-rename
# ones, so this runs after _TABLES.
_COLUMNS = (
    ("hypermesh_gateway_metrics", "router_id", "gateway_id"),
    ("hypermesh_tickets", "assigned_router_id", "assigned_gateway_id"),
    ("hypermesh_tunnels", "assigned_router_id", "assigned_gateway_id"),
)

# ALTER TABLE ... RENAME TO leaves indexes and constraints on their original
# names, so a renamed database and a fresh one would disagree on every one of
# these. A later migration that drops a constraint by name would then work on
# one and fail on the other.
_RELATIONS = (
    ("hypermesh_routers_pkey", "hypermesh_gateways_pkey"),
    ("uq_hm_routers_tenant_name", "uq_hm_gateways_tenant_name"),
    ("ix_hm_routers_tenant", "ix_hm_gateways_tenant"),
    ("hypermesh_router_metrics_pkey", "hypermesh_gateway_metrics_pkey"),
    ("ix_hm_router_metrics_tenant", "ix_hm_gateway_metrics_tenant"),
)

_CONSTRAINTS = (
    (
        "hypermesh_gateways",
        "hypermesh_routers_tenant_id_fkey",
        "hypermesh_gateways_tenant_id_fkey",
    ),
    (
        "hypermesh_gateway_metrics",
        "hypermesh_router_metrics_tenant_id_fkey",
        "hypermesh_gateway_metrics_tenant_id_fkey",
    ),
)


def _rename_tables(pairs: tuple[tuple[str, str], ...]) -> None:
    for old, new in pairs:
        op.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF to_regclass('{old}') IS NOT NULL
                       AND to_regclass('{new}') IS NULL THEN
                        ALTER TABLE {old} RENAME TO {new};
                    END IF;
                END $$
                """
            )
        )


def _rename_columns(triples: tuple[tuple[str, str, str], ...]) -> None:
    for table, old, new in triples:
        op.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = '{table}' AND column_name = '{old}'
                    ) AND NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = '{table}' AND column_name = '{new}'
                    ) THEN
                        ALTER TABLE {table} RENAME COLUMN {old} TO {new};
                    END IF;
                END $$
                """
            )
        )


def _rename_relations(pairs: tuple[tuple[str, str], ...]) -> None:
    """Indexes and unique/primary-key constraints, which share a namespace."""

    for old, new in pairs:
        op.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF to_regclass('{old}') IS NOT NULL
                       AND to_regclass('{new}') IS NULL THEN
                        ALTER INDEX {old} RENAME TO {new};
                    END IF;
                END $$
                """
            )
        )


def _rename_constraints(triples: tuple[tuple[str, str, str], ...]) -> None:
    for table, old, new in triples:
        op.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF to_regclass('{table}') IS NOT NULL AND EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = '{old}'
                          AND conrelid = to_regclass('{table}')
                    ) AND NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = '{new}'
                          AND conrelid = to_regclass('{table}')
                    ) THEN
                        ALTER TABLE {table}
                            RENAME CONSTRAINT {old} TO {new};
                    END IF;
                END $$
                """
            )
        )


def upgrade() -> None:
    _rename_tables(_TABLES)
    _rename_columns(_COLUMNS)
    _rename_relations(_RELATIONS)
    _rename_constraints(_CONSTRAINTS)

    # RLS policies ride along with the table, and both shapes name them
    # tenant_isolation_*, so there is nothing to rename. Assert it instead of
    # assuming it: a gateway table with RLS silently off is a cross-tenant read.
    for _, table in _TABLES:
        op.execute(
            sa.text(
                f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_policies
                        WHERE tablename = '{table}'
                          AND policyname = 'tenant_isolation_select'
                    ) THEN
                        RAISE EXCEPTION
                            '{table} has no tenant_isolation_select policy';
                    END IF;
                END $$
                """
            )
        )

    # 0018 now declares the default as 'gateway', so a fresh database has that
    # and a renamed one still has 'router'.
    op.execute(
        sa.text("ALTER TABLE hypermesh_gateways ALTER COLUMN role SET DEFAULT 'gateway'")
    )

    # PlaneRole no longer has a 'router' member, so a row carrying it fails to
    # load rather than degrading.
    op.execute(sa.text("UPDATE hypermesh_gateways SET role = 'gateway' WHERE role = 'router'"))

    # The seeded gateway is keyed by id, so seeding will not correct its name and
    # the router-era string would outlive the rename. Guarded on the new name
    # being free because (tenant_id, name) is unique.
    op.execute(
        sa.text(
            """
            UPDATE hypermesh_gateways AS g
            SET name = 'fyber-test-gateway'
            WHERE g.name = 'fyber-test-router'
              AND NOT EXISTS (
                  SELECT 1 FROM hypermesh_gateways AS other
                  WHERE other.tenant_id = g.tenant_id
                    AND other.name = 'fyber-test-gateway'
              )
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("UPDATE hypermesh_gateways SET role = 'router' WHERE role = 'gateway'"))
    op.execute(sa.text("ALTER TABLE hypermesh_gateways ALTER COLUMN role SET DEFAULT 'router'"))
    _rename_constraints(tuple((t, new, old) for t, old, new in _CONSTRAINTS))
    _rename_relations(tuple((new, old) for old, new in _RELATIONS))
    _rename_columns(tuple((t, new, old) for t, old, new in _COLUMNS))
    _rename_tables(tuple((new, old) for old, new in _TABLES))
