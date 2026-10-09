"""Version-specific scan evidence and recoverable inspection claims."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "hypermesh_0059_model_inspection"
down_revision = "hypermesh_0058_model_upload"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "hypermesh_model_revisions",
        sa.Column(
            "scan_state", sa.String(16), nullable=False, server_default="pending"
        ),
    )
    op.add_column(
        "hypermesh_model_revisions", sa.Column("scan_evidence", JSONB(), nullable=True)
    )
    op.add_column(
        "hypermesh_model_revisions", sa.Column("inspection", JSONB(), nullable=True)
    )
    op.add_column(
        "hypermesh_model_revisions",
        sa.Column("inspection_failures", JSONB(), nullable=True),
    )
    op.add_column(
        "hypermesh_model_revisions",
        sa.Column("inspection_claim_id", UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "hypermesh_model_revisions",
        sa.Column("inspection_claim_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    raise RuntimeError(
        "Retain scan and inspection evidence; disable workers for rollback"
    )
