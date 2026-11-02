"""Retain offer-time throughput provenance without rewriting historical leases."""
import sqlalchemy as sa
from alembic import op

revision = "hypermesh_0066_receipt_versions"
down_revision = "hypermesh_0065_contract_until"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hypermesh_leases", sa.Column("throughput_map_version", sa.String(96), nullable=True))


def downgrade():
    raise RuntimeError("Receipt provenance must not be discarded")
