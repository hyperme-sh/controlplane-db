"""Admit fiat company/NY/HI profiles without rewriting enrollment history."""

from alembic import op

revision = "payment_service_0066_fiat"
down_revision = "payment_service_0065_method"
branch_labels = None
depends_on = None

NEW = {
    "ck_connect_recipient_legal_type": "legal_type IN ('individual', 'sole_proprietor') OR (payout_method = 'fiat_bank' AND legal_type = 'company')",
    "ck_connect_recipient_state": "(country = 'US' AND state IS NOT NULL AND state IN ('AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL', 'GA', 'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY') AND (payout_method = 'fiat_bank' OR state NOT IN ('NY', 'HI'))) OR (country <> 'US' AND state IS NULL)",
}
OLD = {
    "ck_connect_recipient_legal_type": "legal_type IN ('individual', 'sole_proprietor')",
    "ck_connect_recipient_state": "(country = 'US' AND state IS NOT NULL AND state IN ('AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL', 'GA', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY')) OR (country <> 'US' AND state IS NULL)",
}


def replace(checks):
    for name, condition in checks.items():
        op.drop_constraint(name, "connect_recipient_accounts", type_="check")
        op.create_check_constraint(name, "connect_recipient_accounts", condition)


def upgrade():
    replace(NEW)


def downgrade():
    # No row rewrites, history loss or trigger bypass on downgrade.
    op.execute("SET LOCAL row_security = off")
    op.execute("LOCK TABLE public.connect_recipient_accounts IN ACCESS EXCLUSIVE MODE")
    for condition in OLD.values():
        op.execute(
            "DO $$ BEGIN IF EXISTS (SELECT 1 FROM public.connect_recipient_accounts WHERE NOT ("
            + condition
            + ")) THEN RAISE EXCEPTION 'Cannot remove fiat admission while incompatible recipient history exists'; END IF; END $$;"
        )
    replace(OLD)
