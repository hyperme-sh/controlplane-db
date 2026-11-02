"""Host signing keys, replay protection and short-lived token hashes."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "hypermesh_0055_machine_identity"
down_revision = "hypermesh_0054_cache_capacity"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "hypermesh_host_registrations",
        sa.Column("machine_identity", JSONB(none_as_null=True), nullable=True),
    )


def downgrade():
    # Dropping bound identity state would resurrect retired bootstrap credentials.
    raise RuntimeError(
        "Machine identity downgrade requires an explicit host re-enrollment plan"
    )
