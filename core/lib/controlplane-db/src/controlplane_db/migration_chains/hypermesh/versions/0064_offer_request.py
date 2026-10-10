"""Persist the request binding for retryable lease offers."""
import sqlalchemy as sa
from alembic import op

revision = "hypermesh_0064_offer_request"
down_revision = "hypermesh_0062_model_lifecycle"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("hypermesh_leases", sa.Column("offer_request_sha256", sa.String(64), nullable=True))

def downgrade():
    op.drop_column("hypermesh_leases", "offer_request_sha256")
