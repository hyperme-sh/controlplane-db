"""Owner organization for each site_id, backfilled using bound devices.

A site's owner is the single organization among its active (not archived)
bound devices. A site with no active bound devices, or whose devices belong to
several organizations, keeps owner_org NULL and is logged by tenant and
site_id; host support assigns those owners afterwards. Sites referenced only by
site tokens are included.
"""

import logging
from collections import defaultdict
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "hypermesh_0056_site_owner_org"
down_revision = "hypermesh_0055_machine_identity"
branch_labels = None
depends_on = None

logger = logging.getLogger("controlplane_db.migrations")


def plan_site_owners(device_rows, token_rows):
    """Return [(tenant_id, site_id, owner_org, reason)], sorted.

    device_rows: (tenant_id, site_id, host_org_id, archived) per bound device.
    token_rows: (tenant_id, site_id) per site token.
    reason is None when an owner was found.
    """

    sites = set()
    orgs = defaultdict(set)
    for tenant_id, site_id, host_org_id, archived in device_rows:
        if not site_id:
            continue
        sites.add((tenant_id, site_id))
        if not archived:
            orgs[(tenant_id, site_id)].add(host_org_id)
    for tenant_id, site_id in token_rows:
        if site_id:
            sites.add((tenant_id, site_id))
    plan = []
    for key in sorted(sites, key=lambda item: (str(item[0]), item[1])):
        found = orgs.get(key, set())
        if len(found) == 1:
            plan.append((key[0], key[1], next(iter(found)), None))
        elif not found:
            plan.append((key[0], key[1], None, "no active bound devices"))
        else:
            plan.append((key[0], key[1], None, f"devices from {len(found)} organizations"))
    return plan


def upgrade():
    op.create_table(
        "hypermesh_sites",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("site_id", sa.String(128), primary_key=True),
        sa.Column("owner_org", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        # Set when host support changes the owner; tokens issued earlier stop
        # acting for the site. Backfilled rows leave it NULL.
        sa.Column("owner_set_at", sa.DateTime(timezone=True), nullable=True),
    )
    bind = op.get_bind()
    # Both source tables FORCE row level security, which hides every tenant's
    # rows from the owner while no tenant is set. Lift FORCE only for the read.
    op.execute("ALTER TABLE hypermesh_devices NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE hypermesh_site_tokens NO FORCE ROW LEVEL SECURITY")
    devices = bind.execute(
        sa.text(
            "SELECT tenant_id, site_id, host_org_id, archived_at IS NOT NULL "
            "FROM hypermesh_devices WHERE site_id IS NOT NULL AND site_id <> ''"
        )
    ).all()
    tokens = bind.execute(
        sa.text("SELECT DISTINCT tenant_id, site_id FROM hypermesh_site_tokens")
    ).all()
    op.execute("ALTER TABLE hypermesh_devices FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE hypermesh_site_tokens FORCE ROW LEVEL SECURITY")
    now = datetime.now(UTC)
    plan = plan_site_owners(devices, tokens)
    for tenant_id, site_id, owner_org, reason in plan:
        if reason is not None:
            logger.warning(
                "hypermesh_sites backfill: site %s (tenant %s) owner_org left NULL: %s",
                site_id,
                tenant_id,
                reason,
            )
    if plan:
        sites = sa.table(
            "hypermesh_sites",
            sa.column("tenant_id", postgresql.UUID(as_uuid=True)),
            sa.column("site_id", sa.String(128)),
            sa.column("owner_org", postgresql.UUID(as_uuid=True)),
            sa.column("created_at", sa.DateTime(timezone=True)),
        )
        op.bulk_insert(
            sites,
            [
                {"tenant_id": tenant_id, "site_id": site_id, "owner_org": owner_org, "created_at": now}
                for tenant_id, site_id, owner_org, _ in plan
            ],
        )
    owned = sum(1 for row in plan if row[2] is not None)
    logger.info(
        "hypermesh_sites backfill: %d sites, %d with an owner, %d without",
        len(plan),
        owned,
        len(plan) - owned,
    )
    op.execute("ALTER TABLE hypermesh_sites ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE hypermesh_sites FORCE ROW LEVEL SECURITY")
    predicate = (
        "tenant_id::text = nullif(current_setting('app.current_tenant_id', true), '')"
    )
    for operation in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        clause = (
            f"WITH CHECK ({predicate})"
            if operation == "INSERT"
            else f"USING ({predicate})"
        )
        if operation == "UPDATE":
            clause += f" WITH CHECK ({predicate})"
        op.execute(
            f"CREATE POLICY tenant_isolation_{operation.lower()} ON hypermesh_sites FOR {operation} {clause}"
        )


def downgrade():
    # Earlier code does not read site owners; a later upgrade backfills again.
    op.drop_table("hypermesh_sites")
