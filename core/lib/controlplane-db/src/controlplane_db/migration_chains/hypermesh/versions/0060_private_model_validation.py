"""Private lab assignment and exact admission scope, separate from certification."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "hypermesh_0060_model_validation"
down_revision = "hypermesh_0059_model_inspection"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hypermesh_model_validations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_sub", sa.String(512), nullable=False),
        sa.Column("revision_id", UUID(as_uuid=True), sa.ForeignKey("hypermesh_model_revisions.id"), nullable=False),
        sa.Column("request_id", UUID(as_uuid=True), nullable=False),
        sa.Column("profile_id", sa.String(64), nullable=False),
        sa.Column("target", JSONB(), nullable=False),
        sa.Column("target_sha256", sa.String(64), nullable=False),
        sa.Column("lab_job_id", UUID(as_uuid=True), nullable=False, unique=True),
        sa.Column("lab_device_id", UUID(as_uuid=True), sa.ForeignKey("hypermesh_devices.id"), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("evidence", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", "owner_sub", "request_id", name="uq_hm_validation_request"),
        sa.CheckConstraint("state IN ('planned', 'reported', 'revoked', 'expired')", name="ck_hm_validation_state"),
    )
    op.create_index("ix_hm_validation_owner", "hypermesh_model_validations", ["tenant_id", "owner_sub", "revision_id"])
    op.execute("ALTER TABLE hypermesh_model_validations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE hypermesh_model_validations FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY tenant_isolation ON hypermesh_model_validations
        USING (tenant_id::text = nullif(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id::text = nullif(current_setting('app.current_tenant_id', true), ''))""")


def downgrade():
    raise RuntimeError("Retain private validation evidence; disable delivery for rollback")
