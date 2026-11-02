"""Lease payments are USDC amounts, not a Stripe card session.

Adds the amount in USDC atoms and whether a test-network credit may settle
the payment. Additive only: existing rows keep their gross_cents, and the old
card session id and hosted checkout URL columns stay in place (nullable, no
longer written).
"""

import sqlalchemy as sa
from alembic import op

revision = "hypermesh_0057_lease_usdc"
down_revision = "hypermesh_0056_site_owner_org"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "hypermesh_leases",
        sa.Column("payment_amount_atoms", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "hypermesh_leases",
        sa.Column(
            "payment_test_credit_available",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("hypermesh_leases", "payment_test_credit_available")
    op.drop_column("hypermesh_leases", "payment_amount_atoms")
