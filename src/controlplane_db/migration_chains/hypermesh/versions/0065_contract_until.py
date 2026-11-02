"""Retain owner expiry across restarts; never issue tickets past signed authority."""
import sqlalchemy as sa
from alembic import op
revision = "hypermesh_0065_contract_until"
down_revision = "hypermesh_0064_protection"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("hypermesh_leases", sa.Column("contract_until", sa.DateTime(timezone=True), nullable=True))

def downgrade():
    raise RuntimeError("Owner expiry is required for safe ticket issuance")
