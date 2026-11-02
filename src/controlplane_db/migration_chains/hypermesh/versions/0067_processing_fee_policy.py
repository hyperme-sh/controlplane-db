"""Freeze planning terms before checkout; unknown legacy terms remain NULL."""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "hypermesh_0067_processing_policy"
down_revision = "hypermesh_0066_receipt_versions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hypermesh_leases", sa.Column("processing_fee_policy", postgresql.JSONB(), nullable=True))


def downgrade():
    raise RuntimeError("Original payment terms must not be discarded")
