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
    connection = op.get_bind()
    # Retire the old synthetic fixture by its intake marker, never a device UUID.
    # Preserve history and leave actual enrolled/keyed machines untouched.
    for tenant_id in connection.execute(sa.text("SELECT id FROM tenants")).scalars():
        connection.execute(sa.text("SELECT set_config('app.current_tenant_id', :tenant, true)"),
                           {"tenant": str(tenant_id)})
        connection.execute(sa.text("""
            UPDATE hypermesh_devices SET archived_at = now()
            WHERE tenant_id = :tenant AND NOT enrolled
              AND device_secret_hash IS NULL AND wg_public_key IS NULL
              AND path_a->>'identity' = 'nvidia-agx-orin-64-fyber-lab'
        """), {"tenant": tenant_id})
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
    duplicate = op.get_bind().execute(sa.text("""
        SELECT 1 FROM hypermesh_devices GROUP BY tenant_id, serial HAVING count(*) > 1 LIMIT 1
    """)).first()
    if duplicate:
        raise RuntimeError("Cannot downgrade while archived and replacement hosts share a serial")
    for name in ("uq_hm_devices_tenant_serial", "uq_hm_devices_tenant_host_name", "uq_hm_devices_wg_key"):
        op.drop_index(name, table_name="hypermesh_devices", if_exists=True)
    op.create_unique_constraint("uq_hm_devices_tenant_serial", "hypermesh_devices", ["tenant_id", "serial"])
    op.drop_column("hypermesh_devices", "archived_at")
    op.drop_column("hypermesh_devices", "host_name")
