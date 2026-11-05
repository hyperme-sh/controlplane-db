"""Store original rail and tax-inclusive fee estimates without inventing history."""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "hypermesh_0069_fee_binding"
down_revision = "hypermesh_0068_environment_cert"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hypermesh_leases", sa.Column("processing_fee_binding", postgresql.JSONB(none_as_null=True), nullable=True))


def downgrade():
    raise RuntimeError("Original checkout fee terms must not be discarded")
