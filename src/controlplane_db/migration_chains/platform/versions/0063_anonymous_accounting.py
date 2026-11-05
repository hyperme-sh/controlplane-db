"""Keep global anonymous accounting totals with explicit source units."""

import sqlalchemy as sa
from alembic import op

revision = "platform_0063_anonymous_totals"
down_revision = "platform_0062_financial_clock"
branch_labels = None
depends_on = None

METRICS = "'invoice_paid','charge_captured','refund_paid','processor_cost','tax_collected','tax_refunded','host_gross','host_net','platform_take','host_usdc','lease_delivered','pricing_fill','pricing_tip'"


def upgrade():
    # No tenant, user, order, provider, receipt or timestamp dimensions.
    op.create_table(
        "financial_accounting_totals",
        sa.Column("metric", sa.String(32), primary_key=True),
        sa.Column("currency", sa.String(4), primary_key=True),
        sa.Column("unit", sa.String(16), primary_key=True),
        sa.Column("amount", sa.Numeric(78, 0), nullable=False),
        sa.CheckConstraint(f"metric IN ({METRICS})", name="ck_financial_total_metric"),
        sa.CheckConstraint(
            "(currency ~ '^[A-Z]{3}$' AND unit='minor') OR "
            "(currency='USDC' AND unit IN ('usdc_atom','usdc_cent'))",
            name="ck_financial_total_unit",
        ),
    )

    op.execute("""CREATE FUNCTION public.account_preserve_anonymous_totals()
    RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
    BEGIN
      IF TG_OP IN ('DELETE','TRUNCATE') THEN
        RAISE EXCEPTION 'Anonymous financial totals cannot be discarded';
      END IF;
      IF NEW.metric IS DISTINCT FROM OLD.metric
        OR NEW.currency IS DISTINCT FROM OLD.currency
        OR NEW.unit IS DISTINCT FROM OLD.unit THEN
        RAISE EXCEPTION 'Anonymous financial total dimensions are immutable';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_preserve_anonymous_totals() FROM PUBLIC")
    op.execute("""CREATE TRIGGER financial_totals_preserved BEFORE UPDATE OR DELETE
      ON financial_accounting_totals FOR EACH ROW
      EXECUTE FUNCTION public.account_preserve_anonymous_totals()""")
    op.execute("""CREATE TRIGGER financial_totals_not_truncated BEFORE TRUNCATE
      ON financial_accounting_totals FOR EACH STATEMENT
      EXECUTE FUNCTION public.account_preserve_anonymous_totals()""")


def downgrade():
    # Fence writers before observing emptiness; hold through the DROP.
    op.execute("LOCK TABLE public.financial_accounting_totals IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM public.financial_accounting_totals) THEN
        RAISE EXCEPTION 'Anonymous financial accounting totals must be retained';
      END IF;
    END $$""")
    op.drop_table("financial_accounting_totals")
    op.execute("DROP FUNCTION public.account_preserve_anonymous_totals()")
