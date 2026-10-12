"""Freeze sandbox tax orders and retain original calculation attempts/evidence."""

from alembic import op

revision = "payment_service_0063_tax"
down_revision = "payment_service_0062_mismatch"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
    CREATE TABLE billing_tax_orders (
        revision_id UUID NOT NULL,
        tenant_id UUID NOT NULL,
        billing_record_id UUID NOT NULL,
        seller_id UUID NOT NULL,
        livemode BOOLEAN DEFAULT false NOT NULL,
        supply VARCHAR(32) NOT NULL,
        fee_payer VARCHAR(32) NOT NULL,
        policy_version VARCHAR(72) NOT NULL,
        tax_code VARCHAR(13) NOT NULL,
        subtotal_cents INTEGER NOT NULL,
        country VARCHAR(2) NOT NULL,
        state VARCHAR(200) NOT NULL,
        postal_code VARCHAR(200) NOT NULL,
        city VARCHAR(200) NOT NULL,
        line1 VARCHAR(200) NOT NULL,
        line2 VARCHAR(200) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (revision_id),
        CONSTRAINT uq_tax_order_billing UNIQUE (billing_record_id),
        CONSTRAINT uq_tax_order_scope UNIQUE (revision_id, tenant_id),
        CONSTRAINT ck_tax_order_mode CHECK (NOT livemode),
        CONSTRAINT ck_tax_order_subtotal CHECK (subtotal_cents BETWEEN 1 AND 1000000),
        CONSTRAINT ck_tax_order_commercial CHECK (supply IN ('owned', 'third_party') AND fee_payer IN ('host', 'renter')),
        CONSTRAINT ck_tax_order_policy CHECK (policy_version ~ '^EXAMPLE-[A-Za-z0-9_-]{1,64}$' AND tax_code ~ '^txcd_[0-9]{8}$'),
        CONSTRAINT ck_tax_order_country CHECK (country ~ '^[A-Z]{2}$' AND (country <> 'US' OR state ~ '^[A-Z]{2}$')),
        CONSTRAINT ck_tax_order_address CHECK (length(trim(postal_code)) > 0 AND length(trim(city)) > 0 AND length(trim(line1)) > 0),
        FOREIGN KEY(tenant_id) REFERENCES tenants (id) ON DELETE RESTRICT,
        FOREIGN KEY(billing_record_id) REFERENCES billing_records (id) ON DELETE RESTRICT
    )
    """
    )
    op.execute(
        """
    CREATE TABLE billing_tax_calculations (
        revision_id UUID NOT NULL,
        tenant_id UUID NOT NULL,
        attempted_at TIMESTAMP WITH TIME ZONE NOT NULL,
        status VARCHAR(32) DEFAULT 'attempted' NOT NULL,
        provider_id VARCHAR(208),
        tax_cents INTEGER,
        total_cents INTEGER,
        expires_at TIMESTAMP WITH TIME ZONE,
        breakdown JSONB,
        PRIMARY KEY (revision_id),
        CONSTRAINT fk_tax_calculation_scope FOREIGN KEY(revision_id, tenant_id) REFERENCES billing_tax_orders (revision_id, tenant_id) ON DELETE RESTRICT,
        CONSTRAINT uq_tax_calculation_provider UNIQUE (provider_id),
        CONSTRAINT ck_tax_calculation_status CHECK (status IN ('attempted', 'reconciliation_required', 'bound')),
        CONSTRAINT ck_tax_calculation_id CHECK (provider_id IS NULL OR provider_id ~ '^taxcalc_[A-Za-z0-9_]{1,200}$'),
        CONSTRAINT ck_tax_calculation_evidence CHECK ((status <> 'bound' AND provider_id IS NULL AND tax_cents IS NULL AND total_cents IS NULL AND expires_at IS NULL AND breakdown IS NULL) OR (status = 'bound' AND provider_id IS NOT NULL AND tax_cents IS NOT NULL AND total_cents IS NOT NULL AND expires_at IS NOT NULL AND breakdown IS NOT NULL)),
        CONSTRAINT ck_tax_calculation_quote CHECK (tax_cents BETWEEN 0 AND 1000000 AND total_cents BETWEEN 50 AND 1000000 AND expires_at > attempted_at AND jsonb_typeof(breakdown) = 'array' AND jsonb_array_length(breakdown) > 0)
    )
    """
    )
    for table in ("billing_tax_orders", "billing_tax_calculations"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
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
