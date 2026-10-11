"""Person-wide mismatch loss exposure with account-scoped forced RLS."""

from alembic import op
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Integer,
    String,
    text,
)

revision = "payment_service_0062_mismatch"
down_revision = "payment_service_0061_connect"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payer_mismatch_accounts",
        Column("account_key", String(64), primary_key=True),
        Column("day", Date(), nullable=False),
        Column("mismatches", Integer(), nullable=False, server_default="0"),
        Column("reserved_count", Integer(), nullable=False, server_default="0"),
        Column("reserved_cents", BigInteger(), nullable=False, server_default="0"),
        Column("last_mismatch_at", DateTime(timezone=True)),
        Column("last_checkout_at", DateTime(timezone=True)),
        CheckConstraint(
            "account_key ~ '^[0-9a-f]{64}$'", name="ck_mismatch_account_key"
        ),
        CheckConstraint(
            "mismatches >= 0 AND reserved_count >= 0 AND reserved_cents >= 0",
            name="ck_mismatch_counters",
        ),
        CheckConstraint(
            "reserved_count <= mismatches", name="ck_mismatch_reservations"
        ),
        CheckConstraint(
            "reserved_count <= 2 AND reserved_cents <= 5000", name="ck_mismatch_budget"
        ),
    )
    op.execute("ALTER TABLE payer_mismatch_accounts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE payer_mismatch_accounts FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY mismatch_actor_policy ON payer_mismatch_accounts
        USING (account_key = current_setting('app.payment_mismatch_actor', true))
        WITH CHECK (account_key = current_setting('app.payment_mismatch_actor', true))""")


def downgrade():
    if (
        op.get_bind()
        .execute(text("SELECT EXISTS (SELECT 1 FROM payer_mismatch_accounts)"))
        .scalar()
    ):
        raise RuntimeError(
            "Mismatch exposure counters cannot be discarded by downgrade"
        )
    op.drop_table("payer_mismatch_accounts")
