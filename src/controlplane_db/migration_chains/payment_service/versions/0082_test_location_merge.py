"""Reconcile TEST financial guards with reviewed payout-location evidence.

Both immutable parent migrations remain intact. The branches affect independent
objects; applying either history first must retain its existing data and guards.
"""

revision = "payment_service_0082_test_merge"
down_revision = ("payment_service_0081_test_gc", "payment_service_0081_location")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
