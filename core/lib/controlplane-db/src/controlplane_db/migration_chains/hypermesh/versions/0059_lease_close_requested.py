"""Record when a renter close was claimed.

The claim and its time are written in one conditional update, so a retry of
an unconfirmed settlement uses the original close time. Additive only.
"""

import sqlalchemy as sa
from alembic import op

revision = "hypermesh_0059_lease_close_at"
down_revision = "hypermesh_0058_live_lease_index"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "hypermesh_leases",
        sa.Column("close_requested_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("hypermesh_leases", "close_requested_at")
