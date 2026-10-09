"""Private model revocation, retention audit and trusted storage health."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "hypermesh_0062_model_lifecycle"
down_revision = "hypermesh_0062_payment_claim"
branch_labels = None
depends_on = None


def upgrade():
    for name in ("revoked_at", "delete_requested_at", "retain_until", "cleanup_claim_until"):
        op.add_column(
            "hypermesh_model_revisions",
            sa.Column(name, sa.DateTime(timezone=True), nullable=True),
        )
    op.add_column(
        "hypermesh_model_revisions",
        sa.Column(
            "retention_hold", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "hypermesh_model_revisions",
        sa.Column("lifecycle_audit", JSONB(), nullable=True),
    )
    op.drop_constraint(
        "ck_hm_revision_state", "hypermesh_model_revisions", type_="check"
    )
    op.create_check_constraint(
        "ck_hm_revision_state",
        "hypermesh_model_revisions",
        "state IN ('uploading', 'sealed', 'aborted', 'revoked', 'deleting', 'deleted')",
    )
    op.create_table(
        "hypermesh_model_storage_health",
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("account", sa.String(24), primary_key=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("physical_bytes", sa.BigInteger(), nullable=False),
        sa.Column("version_count", sa.BigInteger(), nullable=False),
        sa.Column("queue_age_seconds", sa.BigInteger(), nullable=False),
        sa.Column("janitor_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("healthy", sa.Boolean(), nullable=False),
    )
    op.execute("ALTER TABLE hypermesh_model_storage_health ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE hypermesh_model_storage_health FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY tenant_isolation ON hypermesh_model_storage_health
        USING (tenant_id::text = nullif(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id::text = nullif(current_setting('app.current_tenant_id', true), ''))""")


def downgrade():
    raise RuntimeError(
        "Retain revocation and retention evidence; disable private uploads for rollback"
    )
