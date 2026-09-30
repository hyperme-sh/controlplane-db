"""Host-reported discovery name and permanent retirement."""
from alembic import op
import sqlalchemy as sa

revision = "0050_host_lifecycle"
down_revision = "0049_idle_tunnel_lease"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("hypermesh_devices", sa.Column("host_name", sa.String(128), nullable=True))
    op.add_column("hypermesh_devices", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    connection = op.get_bind()
    # Retire the old synthetic fixture by its intake marker, never a device UUID.
    # Preserve history and leave actual enrolled/keyed machines untouched.
    for tenant_id in connection.execute(sa.text("SELECT id FROM tenants")).scalars():
        connection.execute(sa.text("SELECT set_config('app.tenant_id', :tenant, true)"),
                           {"tenant": str(tenant_id)})
        connection.execute(sa.text("""
            UPDATE hypermesh_devices SET archived_at = now()
            WHERE tenant_id = :tenant AND NOT enrolled
              AND device_secret_hash IS NULL AND wg_public_key IS NULL
              AND path_a->>'identity' = 'nvidia-agx-orin-64-fyber-lab'
        """), {"tenant": tenant_id})
    op.drop_constraint("uq_hm_devices_tenant_serial", "hypermesh_devices", type_="unique")
    op.create_index("uq_hm_devices_tenant_serial", "hypermesh_devices",
                    ["tenant_id", "serial"], unique=True,
                    postgresql_where=sa.text("archived_at IS NULL"))
    op.create_index("uq_hm_devices_tenant_host_name", "hypermesh_devices",
                    ["tenant_id", "host_name"], unique=True,
                    postgresql_where=sa.text("archived_at IS NULL AND enrolled AND host_name IS NOT NULL"))
    op.create_index("uq_hm_devices_wg_key", "hypermesh_devices",
                    ["wg_public_key"], unique=True,
                    postgresql_where=sa.text("wg_public_key IS NOT NULL"))


def downgrade() -> None:
    # Retirement history may now share a serial with its replacement.
    # Do not destroy that history to restore the old uniqueness rule.
    raise RuntimeError("Host retirement migration requires a forward repair")
