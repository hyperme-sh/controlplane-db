"""Realm-wide account retirement, scoped receipts and API-key issuer fencing."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "platform_0059_account_lifecycles"
down_revision = "platform_0058_closure_requests"
branch_labels = None
depends_on = None


def upgrade():
    # Principal retirement is global to the one pinned realm. Tenant RLS must
    # not hide a tombstone during authentication in another membership.
    op.create_table(
        "account_lifecycles",
        sa.Column("subject", sa.String(512), primary_key=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_by", sa.String(512), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("profile_deleted_at", sa.DateTime(timezone=True)),
        sa.Column("financial_deleted_at", sa.DateTime(timezone=True)),
        sa.Column("financial_retain_until", sa.DateTime(timezone=True)),
        sa.Column("financial_hold", sa.Boolean(), nullable=False),
        sa.Column("hold_reference", sa.String(128)),
        sa.Column("claim_id", UUID(as_uuid=True)),
        sa.Column("claim_until", sa.DateTime(timezone=True)),
        sa.Column("retry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(64)),
        sa.Column("effects", JSONB(), nullable=False),
        sa.CheckConstraint(
            "state IN ('closing','closed','deleting','deleted')",
            name="ck_account_lifecycle_state",
        ),
        sa.CheckConstraint(
            "length(btrim(subject)) > 0", name="ck_account_lifecycle_subject"
        ),
    )
    op.create_index(
        "ix_account_lifecycle_work", "account_lifecycles", ["state", "retry_at"]
    )
    op.create_table(
        "account_lifecycle_scopes",
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "subject",
            sa.String(512),
            sa.ForeignKey("account_lifecycles.subject", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("user_ids", JSONB(), nullable=False),
        sa.Column("effects", JSONB(), nullable=False),
    )
    op.create_table(
        "identity_retirements",
        sa.Column("subject", sa.String(512), primary_key=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "api_key_owner_closures",
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("subject", sa.String(512), primary_key=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
    )
    for table in ("account_lifecycle_scopes", "api_key_owner_closures"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id::text = nullif(current_setting('app.current_tenant_id',true),''))
            WITH CHECK (tenant_id::text = nullif(current_setting('app.current_tenant_id',true),''))""")


def downgrade():
    # Downgrading an unused, default-off installation is safe. Recorded
    # retirement/credential tombstones are permanent. With forced RLS this
    # either sees every row or PostgreSQL refuses the read; never hide data
    # behind the current tenant while deciding that an installation is empty.
    op.execute("SET LOCAL row_security = off")
    for table in (
        "account_lifecycle_scopes",
        "api_key_owner_closures",
        "identity_retirements",
        "account_lifecycles",
    ):
        if (
            op.get_bind()
            .execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})"))
            .scalar_one()
        ):
            raise RuntimeError(
                "Account retirement and credential tombstones cannot be discarded"
            )
    op.drop_table("account_lifecycle_scopes")
    op.drop_table("api_key_owner_closures")
    op.drop_table("identity_retirements")
    op.drop_table("account_lifecycles")
