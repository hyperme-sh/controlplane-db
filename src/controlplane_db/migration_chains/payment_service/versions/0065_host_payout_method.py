"""Persist host payout policy without replacing enrollment/account history."""

import sqlalchemy as sa
from alembic import op

revision = "payment_service_0065_method"
down_revision = "payment_service_0064_retire"
branch_labels = None
depends_on = None


def upgrade():
    # Existing immutable-history triggers compare all columns. Adding columns
    # with constant defaults backfills atomically without UPDATE or trigger bypass.
    op.add_column(
        "connect_recipient_accounts",
        sa.Column(
            "payout_method", sa.String(16), nullable=False, server_default="fiat_bank"
        ),
    )
    op.add_column(
        "connect_recipient_accounts",
        sa.Column(
            "eligibility_rule_version",
            sa.String(64),
            nullable=False,
            server_default="fiat-us/v1",
        ),
    )
    op.create_check_constraint(
        "ck_connect_recipient_payout_policy",
        "connect_recipient_accounts",
        "(payout_method = 'fiat_bank' AND eligibility_rule_version = 'fiat-us/v1') OR (payout_method = 'usdc' AND eligibility_rule_version = 'usdc-stablecoin/v1')",
    )


def downgrade():
    # Removing admission policy would lose immutable enrollment provenance.
    op.execute("SET LOCAL row_security = off")
    op.execute("LOCK TABLE public.connect_recipient_accounts IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM public.connect_recipient_accounts) THEN
            RAISE EXCEPTION 'Cannot remove payout policy from nonempty Connect history';
        END IF;
    END $$;""")
    op.drop_constraint(
        "ck_connect_recipient_payout_policy",
        "connect_recipient_accounts",
        type_="check",
    )
    op.drop_column("connect_recipient_accounts", "eligibility_rule_version")
    op.drop_column("connect_recipient_accounts", "payout_method")
