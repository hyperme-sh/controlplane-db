"""Retain sandbox Connect creation attempts and immutable account bindings."""

from alembic import op
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

revision = "payment_service_0061_connect"
down_revision = "payment_service_0060_onramp"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "connect_recipient_accounts",
        Column(
            "tenant_id",
            UUID(as_uuid=True),
            ForeignKey("tenants.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        Column("host_org_id", UUID(as_uuid=True), primary_key=True),
        Column("livemode", Boolean(), server_default=false(), nullable=False),
        Column("attempt_id", UUID(as_uuid=True), nullable=False),
        Column("attempted_at", DateTime(timezone=True), nullable=False),
        Column("legal_type", String(32), nullable=False),
        Column("country", String(2), nullable=False),
        Column("state", String(2), nullable=True),
        Column("stripe_account_id", String(255), nullable=True),
        Column(
            "creation_status",
            String(32),
            server_default="pending_creation",
            nullable=False,
        ),
        Column("capability_status", String(64), nullable=True),
        Column("capability_observed_at", DateTime(timezone=True), nullable=True),
        Column(
            "created_at",
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
        CheckConstraint("NOT livemode", name="ck_connect_recipient_mode"),
        CheckConstraint(
            "legal_type IN ('individual', 'sole_proprietor')",
            name="ck_connect_recipient_legal_type",
        ),
        CheckConstraint("country ~ '^[A-Z]{2}$'", name="ck_connect_recipient_country"),
        CheckConstraint(
            "(country = 'US' AND state IS NOT NULL AND state IN ('AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL', 'GA', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY')) OR (country <> 'US' AND state IS NULL)",
            name="ck_connect_recipient_state",
        ),
        CheckConstraint(
            "stripe_account_id IS NULL OR stripe_account_id ~ '^acct_[A-Za-z0-9]+$'",
            name="ck_connect_recipient_account",
        ),
        CheckConstraint(
            "(creation_status = 'bound' AND stripe_account_id IS NOT NULL) OR (creation_status IN ('pending_creation', 'reconciliation_required') AND stripe_account_id IS NULL)",
            name="ck_connect_recipient_binding",
        ),
        CheckConstraint(
            "(capability_status IS NULL AND capability_observed_at IS NULL) OR (stripe_account_id IS NOT NULL AND capability_status IS NOT NULL AND length(trim(capability_status)) > 0 AND capability_observed_at IS NOT NULL)",
            name="ck_connect_recipient_observation",
        ),
        UniqueConstraint("attempt_id", name="uq_connect_recipient_attempt"),
        UniqueConstraint("stripe_account_id", name="uq_connect_recipient_account"),
    )
    op.execute("ALTER TABLE connect_recipient_accounts ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE connect_recipient_accounts FORCE ROW LEVEL SECURITY")
    scope = (
        "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
    )
    for operation, clause in (
        ("SELECT", f"USING ({scope})"),
        ("INSERT", f"WITH CHECK ({scope})"),
        ("UPDATE", f"USING ({scope}) WITH CHECK ({scope})"),
        ("DELETE", f"USING ({scope})"),
    ):
        op.execute(
            f"CREATE POLICY connect_recipient_{operation.lower()} ON connect_recipient_accounts FOR {operation} {clause}"
        )
    op.execute("""
    CREATE FUNCTION public.connect_recipient_immutable() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    BEGIN
      RAISE EXCEPTION 'Connect recipient history cannot be removed' USING ERRCODE = '23514';
    END $$;
    CREATE FUNCTION public.connect_recipient_progress_only() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    BEGIN
      IF (to_jsonb(NEW) - 'stripe_account_id' - 'creation_status' - 'capability_status' - 'capability_observed_at') IS DISTINCT FROM
         (to_jsonb(OLD) - 'stripe_account_id' - 'creation_status' - 'capability_status' - 'capability_observed_at') OR
         (OLD.stripe_account_id IS NOT NULL AND NEW.stripe_account_id IS DISTINCT FROM (OLD.stripe_account_id)) OR
         (OLD.creation_status = 'reconciliation_required' AND NEW.creation_status = 'pending_creation') OR
         (OLD.capability_observed_at IS NOT NULL AND
           (NEW.capability_observed_at IS NULL OR NEW.capability_observed_at < OLD.capability_observed_at OR
            (NEW.capability_status IS DISTINCT FROM (OLD.capability_status) AND NEW.capability_observed_at <= OLD.capability_observed_at))) THEN
        RAISE EXCEPTION 'Connect recipient history cannot be rewritten' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER connect_recipient_progress BEFORE UPDATE ON public.connect_recipient_accounts FOR EACH ROW EXECUTE FUNCTION public.connect_recipient_progress_only();
    CREATE TRIGGER connect_recipient_delete BEFORE DELETE ON public.connect_recipient_accounts FOR EACH ROW EXECUTE FUNCTION public.connect_recipient_immutable();
    CREATE TRIGGER connect_recipient_truncate BEFORE TRUNCATE ON public.connect_recipient_accounts FOR EACH STATEMENT EXECUTE FUNCTION public.connect_recipient_immutable();
    """)


def downgrade():
    op.execute("SET LOCAL row_security = off")
    op.execute("LOCK TABLE public.connect_recipient_accounts IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM public.connect_recipient_accounts) THEN
            RAISE EXCEPTION 'Cannot remove nonempty Connect recipient history';
        END IF;
    END $$;""")
    op.drop_table("connect_recipient_accounts")
    op.execute("DROP FUNCTION public.connect_recipient_progress_only()")
    op.execute("DROP FUNCTION public.connect_recipient_immutable()")
