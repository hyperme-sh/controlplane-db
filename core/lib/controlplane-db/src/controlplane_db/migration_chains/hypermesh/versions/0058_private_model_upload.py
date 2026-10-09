"""Durable private model uploads; RLS and sealed version identity."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "hypermesh_0058_model_upload"
down_revision = "hypermesh_0059_lease_close_at"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hypermesh_model_revisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_sub", sa.String(512), nullable=False),
        sa.Column("request_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("license", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("manifest", JSONB(), nullable=False),
        sa.Column("storage_account", sa.String(24), nullable=False),
        sa.Column("storage_container", sa.String(63), nullable=False),
        sa.Column("sealed_files", JSONB(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "owner_sub", "request_id", name="uq_hm_revision_request"
        ),
        sa.CheckConstraint(
            "size_bytes > 0 AND size_bytes <= 50000000000", name="ck_hm_revision_size"
        ),
        sa.CheckConstraint(
            "state IN ('uploading', 'sealed', 'aborted')", name="ck_hm_revision_state"
        ),
    )
    op.create_index(
        "ix_hm_revision_owner",
        "hypermesh_model_revisions",
        ["tenant_id", "owner_sub", "created_at"],
    )
    op.execute("ALTER TABLE hypermesh_model_revisions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE hypermesh_model_revisions FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY tenant_isolation ON hypermesh_model_revisions
        USING (tenant_id::text = nullif(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id::text = nullif(current_setting('app.current_tenant_id', true), ''))""")


def downgrade():
    raise RuntimeError(
        "Retain sealed revision evidence; disable upload feature for rollback"
    )
