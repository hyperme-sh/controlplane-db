"""Preserve sandbox history; freeze explicit live mode and counsel reference."""

import sqlalchemy as sa
from alembic import op

revision = "payment_service_0074_live"
down_revision = "payment_service_0073_fiat_pr"
branch_labels = None
depends_on = None
CONDITION = "(NOT livemode AND live_approval_reference IS NULL) OR (livemode AND COALESCE(length(trim(live_approval_reference)) BETWEEN 1 AND 2048, false))"


def upgrade():
    op.add_column(
        "connect_recipient_accounts",
        sa.Column("live_approval_reference", sa.String(2048), nullable=True),
    )
    op.drop_constraint(
        "ck_connect_recipient_mode", "connect_recipient_accounts", type_="check"
    )
    op.create_check_constraint(
        "ck_connect_recipient_mode", "connect_recipient_accounts", CONDITION
    )
    # Choose initial disabled access policy only for new rows. Existing account
    # and access-state history is never backfilled or silently activated.
    access_policy(
        "CASE WHEN NEW.livemode THEN 'embedded-api/v1' ELSE 'express-probe/v1' END"
    )


def access_policy(expression):
    op.execute(
        """CREATE OR REPLACE FUNCTION public.connect_access_legacy() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$ BEGIN
        INSERT INTO public.connect_access_states(tenant_id,host_org_id,policy)
        VALUES (NEW.tenant_id,NEW.host_org_id,"""
        + expression
        + """); RETURN NEW;
        END $$"""
    )


def downgrade():
    # Fail rather than hide other tenants behind row-level security or discard authority.
    op.execute("LOCK TABLE connect_recipient_accounts IN ACCESS EXCLUSIVE MODE")
    op.execute("SET LOCAL row_security = off")
    if (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT EXISTS (SELECT 1 FROM connect_recipient_accounts WHERE livemode)"
            )
        )
        .scalar()
    ):
        raise RuntimeError("Cannot downgrade while live recipient history exists")
    op.drop_constraint(
        "ck_connect_recipient_mode", "connect_recipient_accounts", type_="check"
    )
    op.create_check_constraint(
        "ck_connect_recipient_mode", "connect_recipient_accounts", "NOT livemode"
    )
    access_policy("'express-probe/v1'")
    op.drop_column("connect_recipient_accounts", "live_approval_reference")
