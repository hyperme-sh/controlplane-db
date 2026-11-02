"""Host-reported discovery name and permanent retirement."""
from alembic import op
import sqlalchemy as sa

revision = "0050_host_lifecycle"
down_revision = "0049_idle_tunnel_lease"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE hypermesh_devices ADD COLUMN IF NOT EXISTS host_name VARCHAR(128)")
    op.execute("ALTER TABLE hypermesh_devices ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ")
    # Keep the data repair in SQL so offline plans contain the same work.
    # Apply tenant scope for forced RLS and restore the caller's setting.
    op.execute("""
        DO $migration$
        DECLARE
            target_tenant UUID;
            previous_tenant TEXT := current_setting('app.current_tenant_id', true);
        BEGIN
            FOR target_tenant IN SELECT id FROM tenants LOOP
                PERFORM set_config('app.current_tenant_id', target_tenant::text, true);
                UPDATE hypermesh_devices SET archived_at = now()
                WHERE tenant_id = target_tenant AND NOT enrolled
                  AND device_secret_hash IS NULL AND wg_public_key IS NULL
                  AND path_a->>'identity' = 'nvidia-agx-orin-64-fyber-lab';
            END LOOP;
            PERFORM set_config('app.current_tenant_id', coalesce(previous_tenant, ''), true);
        END;
        $migration$;
    """)
    op.execute("ALTER TABLE hypermesh_devices DROP CONSTRAINT IF EXISTS uq_hm_devices_tenant_serial")
    op.create_index("uq_hm_devices_tenant_serial", "hypermesh_devices",
                    ["tenant_id", "serial"], unique=True, if_not_exists=True,
                    postgresql_where=sa.text("archived_at IS NULL"))
    op.create_index("uq_hm_devices_tenant_host_name", "hypermesh_devices",
                    ["tenant_id", "host_name"], unique=True, if_not_exists=True,
                    postgresql_where=sa.text("archived_at IS NULL AND enrolled AND host_name IS NOT NULL"))
    op.create_index("uq_hm_devices_wg_key", "hypermesh_devices",
                    ["wg_public_key"], unique=True, if_not_exists=True,
                    postgresql_where=sa.text("wg_public_key IS NOT NULL"))


def downgrade() -> None:
    # Refuse downgrade if restoring the old uniqueness rule would discard history.
    op.execute("""
        DO $migration$
        DECLARE
            target_tenant UUID;
            previous_tenant TEXT := current_setting('app.current_tenant_id', true);
        BEGIN
            FOR target_tenant IN SELECT id FROM tenants LOOP
                PERFORM set_config('app.current_tenant_id', target_tenant::text, true);
                IF EXISTS (
                    SELECT 1 FROM hypermesh_devices
                    WHERE tenant_id = target_tenant
                    GROUP BY serial HAVING count(*) > 1
                ) THEN
                    RAISE EXCEPTION 'Cannot downgrade while archived and replacement hosts share a serial';
                END IF;
            END LOOP;
            PERFORM set_config('app.current_tenant_id', coalesce(previous_tenant, ''), true);
        END;
        $migration$;
    """)
    for name in ("uq_hm_devices_tenant_serial", "uq_hm_devices_tenant_host_name", "uq_hm_devices_wg_key"):
        op.drop_index(name, table_name="hypermesh_devices", if_exists=True)
    op.create_unique_constraint("uq_hm_devices_tenant_serial", "hypermesh_devices", ["tenant_id", "serial"])
    op.drop_column("hypermesh_devices", "archived_at")
    op.drop_column("hypermesh_devices", "host_name")
