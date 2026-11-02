"""Align payout evidence actors with the 512-character host identity contract."""

import sqlalchemy as sa
from alembic import op

revision = "payment_service_0055_subject"
down_revision = "payment_service_0054_payout_addr"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "host_payout_addresses",
        "verified_by_sub",
        existing_type=sa.String(256),
        type_=sa.String(512),
        existing_nullable=False,
    )
    op.drop_constraint(
        "ck_payout_address_subject", "host_payout_addresses", type_="check"
    )
    op.create_check_constraint(
        "ck_payout_address_subject",
        "host_payout_addresses",
        "length(verified_by_sub) BETWEEN 1 AND 512",
    )


def downgrade():
    op.drop_constraint(
        "ck_payout_address_subject", "host_payout_addresses", type_="check"
    )
    # Validate before narrowing: rollback rather than truncate existing identities.
    op.create_check_constraint(
        "ck_payout_address_subject",
        "host_payout_addresses",
        "length(verified_by_sub) BETWEEN 1 AND 256",
    )
    op.alter_column(
        "host_payout_addresses",
        "verified_by_sub",
        existing_type=sa.String(512),
        type_=sa.String(256),
        existing_nullable=False,
    )
