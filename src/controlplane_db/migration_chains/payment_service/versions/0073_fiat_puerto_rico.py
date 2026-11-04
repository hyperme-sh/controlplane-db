"""Admit Puerto Rico for fiat without changing old recipient history."""

import sqlalchemy as sa
from alembic import op

revision = "payment_service_0073_fiat_pr"
down_revision = "payment_service_0072_contact"
branch_labels = None
depends_on = None

OLD = "(country = 'US' AND state IS NOT NULL AND state IN ('AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY') AND (payout_method = 'fiat_bank' OR state NOT IN ('NY', 'HI'))) OR (country <> 'US' AND state IS NULL)"
NEW = "(country = 'US' AND state IS NOT NULL AND state IN ('AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY') AND (payout_method = 'fiat_bank' OR state NOT IN ('NY', 'HI'))) OR (country <> 'US' AND state IS NULL) OR (country = 'US' AND payout_method = 'fiat_bank' AND state IS NOT NULL AND state = 'PR')"


def replace(condition):
    op.drop_constraint("ck_connect_recipient_state", "connect_recipient_accounts", type_="check")
    op.create_check_constraint("ck_connect_recipient_state", "connect_recipient_accounts", condition)


def upgrade():
    replace(NEW)


def downgrade():
    if op.get_bind().execute(sa.text(
        "SELECT EXISTS (SELECT 1 FROM connect_recipient_accounts WHERE country = 'US' AND state = 'PR')"
    )).scalar():
        raise RuntimeError("Cannot remove Puerto Rico admission while recipient history exists")
    replace(OLD)
