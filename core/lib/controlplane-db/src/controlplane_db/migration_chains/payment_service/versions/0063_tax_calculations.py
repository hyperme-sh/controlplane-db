"""Freeze sandbox tax orders and retain original calculation attempts/evidence."""

from alembic import op
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "payment_service_0063_tax"
down_revision = "payment_service_0062_mismatch"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "billing_tax_orders",
        Column("revision_id", UUID(as_uuid=True), primary_key=True),
        Column(
            "tenant_id",
            UUID(as_uuid=True),
            ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        Column(
            "billing_record_id",
            UUID(as_uuid=True),
            ForeignKey("billing_records.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        Column("seller_id", UUID(as_uuid=True), nullable=False),
        Column("livemode", Boolean(), nullable=False, server_default=false()),
        Column("supply", String(32), nullable=False),
        Column("fee_payer", String(32), nullable=False),
        Column("policy_version", String(72), nullable=False),
        Column("tax_code", String(13), nullable=False),
        Column("subtotal_cents", Integer(), nullable=False),
        Column("country", String(2), nullable=False),
        Column("state", String(200), nullable=False),
        Column("postal_code", String(200), nullable=False),
        Column("city", String(200), nullable=False),
        Column("line1", String(200), nullable=False),
        Column("line2", String(200), nullable=False),
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
        CheckConstraint(
            "length(trim(postal_code)) > 0 AND length(trim(city)) > 0 AND length(trim(line1)) > 0",
            name="ck_tax_order_address",
        ),
        CheckConstraint(
            "supply IN ('owned', 'third_party') AND fee_payer IN ('host', 'renter')",
            name="ck_tax_order_commercial",
        ),
        CheckConstraint(
            "country ~ '^[A-Z]{2}$' AND (country <> 'US' OR state ~ '^[A-Z]{2}$')",
            name="ck_tax_order_country",
        ),
        CheckConstraint("NOT livemode", name="ck_tax_order_mode"),
        CheckConstraint(
            "policy_version ~ '^EXAMPLE-[A-Za-z0-9_-]{1,64}$' AND tax_code ~ '^txcd_[0-9]{8}$'",
            name="ck_tax_order_policy",
        ),
        CheckConstraint(
            "subtotal_cents BETWEEN 1 AND 1000000", name="ck_tax_order_subtotal"
        ),
        UniqueConstraint("billing_record_id", name="uq_tax_order_billing"),
        UniqueConstraint("revision_id", "tenant_id", name="uq_tax_order_scope"),
    )
    op.create_table(
        "billing_tax_calculations",
        Column("revision_id", UUID(as_uuid=True), primary_key=True),
        Column("tenant_id", UUID(as_uuid=True), nullable=False),
        Column("attempted_at", DateTime(timezone=True), nullable=False),
        Column("status", String(32), nullable=False, server_default="attempted"),
        Column("provider_id", String(208), nullable=True),
        Column("tax_cents", Integer(), nullable=True),
        Column("total_cents", Integer(), nullable=True),
        Column("expires_at", DateTime(timezone=True), nullable=True),
        Column("breakdown", JSONB(), nullable=True),
        CheckConstraint(
            "(status <> 'bound' AND provider_id IS NULL AND tax_cents IS NULL AND total_cents IS NULL AND expires_at IS NULL AND breakdown IS NULL) OR (status = 'bound' AND provider_id IS NOT NULL AND tax_cents IS NOT NULL AND total_cents IS NOT NULL AND expires_at IS NOT NULL AND breakdown IS NOT NULL)",
            name="ck_tax_calculation_evidence",
        ),
        CheckConstraint(
            "provider_id IS NULL OR provider_id ~ '^taxcalc_[A-Za-z0-9_]{1,200}$'",
            name="ck_tax_calculation_id",
        ),
        CheckConstraint(
            "tax_cents BETWEEN 0 AND 1000000 AND total_cents BETWEEN 50 AND 1000000 AND expires_at > attempted_at AND jsonb_typeof(breakdown) = 'array' AND jsonb_array_length(breakdown) > 0",
            name="ck_tax_calculation_quote",
        ),
        CheckConstraint(
            "status IN ('attempted', 'reconciliation_required', 'bound')",
            name="ck_tax_calculation_status",
        ),
        ForeignKeyConstraint(
            ["revision_id", "tenant_id"],
            ["billing_tax_orders.revision_id", "billing_tax_orders.tenant_id"],
            name="fk_tax_calculation_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("provider_id", name="uq_tax_calculation_provider"),
    )
    for table in ("billing_tax_orders", "billing_tax_calculations"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        scope = "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
        op.execute(
            f"CREATE POLICY {table}_tenant ON public.{table} USING ({scope}) WITH CHECK ({scope})"
        )
    op.execute("""
    CREATE FUNCTION public.tax_history_retained() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    BEGIN
      RAISE EXCEPTION 'Tax history cannot be removed or rewritten' USING ERRCODE = '23514';
    END $$;
    CREATE TRIGGER tax_order_update BEFORE UPDATE ON public.billing_tax_orders FOR EACH ROW EXECUTE FUNCTION public.tax_history_retained();
    CREATE FUNCTION public.tax_order_binding() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    BEGIN
      IF NOT EXISTS (SELECT 1 FROM public.billing_records b WHERE b.id = NEW.billing_record_id
        AND b.tenant_id = NEW.tenant_id AND b.scope = 'lease' AND b.payment_type = 'usdc'
        AND b.amount = NEW.subtotal_cents AND b.status = 'pending'
        AND b.stripe_session_id IS NULL AND NOT (b.metadata ? 'stripe_checkout_attempted_at') FOR UPDATE) THEN
        RAISE EXCEPTION 'Tax order requires an unattempted matching pending payment' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER tax_order_insert BEFORE INSERT ON public.billing_tax_orders FOR EACH ROW EXECUTE FUNCTION public.tax_order_binding();
    CREATE FUNCTION public.tax_calculation_progress() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    BEGIN
      IF TG_OP = 'INSERT' AND (NEW.status <> 'attempted' OR NEW.provider_id IS NOT NULL) THEN
        RAISE EXCEPTION 'Tax calculation must start with a retained attempt' USING ERRCODE = '23514';
      END IF;
      IF TG_OP = 'UPDATE' AND (
        ROW(NEW.revision_id, NEW.tenant_id, NEW.attempted_at) IS DISTINCT FROM ROW(OLD.revision_id, OLD.tenant_id, OLD.attempted_at)
        OR (OLD.status = 'reconciliation_required' AND NEW.status = 'attempted')
        OR (OLD.status = 'bound' AND NEW IS DISTINCT FROM OLD)) THEN
        RAISE EXCEPTION 'Tax calculation history cannot be rewritten' USING ERRCODE = '23514';
      END IF;
      IF NEW.status = 'bound' AND NOT EXISTS (SELECT 1 FROM public.billing_tax_orders o
        WHERE o.revision_id = NEW.revision_id AND o.tenant_id = NEW.tenant_id
        AND NEW.total_cents = o.subtotal_cents + NEW.tax_cents) THEN
        RAISE EXCEPTION 'Tax calculation total differs from order' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER tax_calculation_progress BEFORE INSERT OR UPDATE ON public.billing_tax_calculations FOR EACH ROW EXECUTE FUNCTION public.tax_calculation_progress();
    """)
    for table in ("billing_tax_orders", "billing_tax_calculations"):
        for action in ("DELETE", "TRUNCATE"):
            scope = "ROW" if action == "DELETE" else "STATEMENT"
            op.execute(
                f"CREATE TRIGGER {table}_{action.lower()} BEFORE {action} ON public.{table} FOR EACH {scope} EXECUTE FUNCTION public.tax_history_retained()"
            )


def downgrade():
    op.execute("SET LOCAL row_security = off")
    op.execute(
        "LOCK TABLE public.billing_tax_orders, public.billing_tax_calculations IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM public.billing_tax_orders) OR EXISTS (SELECT 1 FROM public.billing_tax_calculations) THEN
        RAISE EXCEPTION 'Cannot remove nonempty tax history';
      END IF;
    END $$;""")
    op.drop_table("billing_tax_calculations")
    op.drop_table("billing_tax_orders")
    for function in (
        "tax_calculation_progress",
        "tax_order_binding",
        "tax_history_retained",
    ):
        op.execute(f"DROP FUNCTION public.{function}()")
