"""Record billing financial activity and ignore observation retry bookkeeping."""

import sqlalchemy as sa
from alembic import op

revision = "platform_0062_financial_clock"
down_revision = "platform_0061_financial_guard"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("billing_records", sa.Column("financial_activity_at", sa.DateTime(timezone=True)))
    op.add_column("billing_records", sa.Column("financial_retain_until", sa.DateTime(timezone=True)))
    # Preserve historical activity. Neither deployment nor closure restarts it.
    op.execute("""UPDATE billing_records
      SET financial_activity_at=coalesce(updated_at,created_at),
          financial_retain_until=((coalesce(updated_at,created_at) AT TIME ZONE 'UTC')
            + interval '7 years') AT TIME ZONE 'UTC'""")
    op.alter_column("billing_records", "financial_activity_at", nullable=False)
    op.alter_column("billing_records", "financial_retain_until", nullable=False)
    op.create_index("ix_billing_financial_due", "billing_records", ["financial_retain_until", "id"])
    op.execute("""CREATE FUNCTION public.account_billing_financial_metadata(p_metadata jsonb)
    RETURNS jsonb LANGUAGE plpgsql IMMUTABLE SET search_path=pg_catalog AS $$
    DECLARE cleaned jsonb := coalesce(p_metadata,'{}'::jsonb); value jsonb;
    BEGIN
      IF jsonb_typeof(cleaned)<>'object' THEN RETURN cleaned; END IF;
      IF jsonb_typeof(cleaned->'stripe_refund_recovery')='object' THEN
        value := (cleaned->'stripe_refund_recovery') - ARRAY[
          'status','operator_required','reason','provider_status','error','checked_at','retry_at','failures'];
        IF value='{}'::jsonb THEN cleaned := cleaned-'stripe_refund_recovery';
        ELSE cleaned := jsonb_set(cleaned,ARRAY['stripe_refund_recovery'],value); END IF;
      END IF;
      IF jsonb_typeof(cleaned->'stripe_fee_accounting')='object' THEN
        value := (cleaned->'stripe_fee_accounting') - ARRAY['status','error','checked_at','retry_at'];
        IF value='{}'::jsonb THEN cleaned := cleaned-'stripe_fee_accounting';
        ELSE cleaned := jsonb_set(cleaned,ARRAY['stripe_fee_accounting'],value); END IF;
      END IF;
      IF jsonb_typeof(cleaned->'stripe_fee_accounting'->'observation'->'standalone_fee_report')='object' THEN
        cleaned := jsonb_set(cleaned,ARRAY['stripe_fee_accounting','observation','standalone_fee_report'],
          (cleaned->'stripe_fee_accounting'->'observation'->'standalone_fee_report') - 'data_available_end');
      END IF;
      RETURN cleaned;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_billing_financial_metadata(jsonb) FROM PUBLIC")
    # Exclude only known operational fields belonging to the two read collectors.
    # Financial evidence and unknown fields, including nested ones, stay significant.
    op.execute("""CREATE FUNCTION public.account_billing_financial_clock()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
    BEGIN
      IF TG_OP='INSERT' THEN
        NEW.financial_activity_at := clock_timestamp();
      ELSE
        IF NEW.financial_activity_at IS DISTINCT FROM OLD.financial_activity_at
          OR NEW.financial_retain_until IS DISTINCT FROM OLD.financial_retain_until THEN
          RAISE EXCEPTION 'Billing financial retention clock is owner recorded';
        END IF;
        IF (to_jsonb(NEW) - ARRAY['updated_at','financial_activity_at','financial_retain_until','metadata'])
            IS DISTINCT FROM
            (to_jsonb(OLD) - ARRAY['updated_at','financial_activity_at','financial_retain_until','metadata'])
          OR public.account_billing_financial_metadata(NEW.metadata)
            IS DISTINCT FROM public.account_billing_financial_metadata(OLD.metadata) THEN
          NEW.financial_activity_at := greatest(OLD.financial_activity_at,clock_timestamp());
        END IF;
      END IF;
      NEW.financial_retain_until := ((NEW.financial_activity_at AT TIME ZONE 'UTC')
        + interval '7 years') AT TIME ZONE 'UTC';
      RETURN NEW;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_billing_financial_clock() FROM PUBLIC")
    op.execute("""CREATE TRIGGER billing_financial_clock BEFORE INSERT OR UPDATE ON billing_records
      FOR EACH ROW EXECUTE FUNCTION public.account_billing_financial_clock()""")
    op.execute("""CREATE FUNCTION public.account_assert_financial_clock_removable()
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog
    SET row_security=off AS $$ BEGIN
      IF EXISTS(SELECT 1 FROM public.billing_records) THEN
        RAISE EXCEPTION 'Recorded financial activity clocks cannot be discarded';
      END IF;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_assert_financial_clock_removable() FROM PUBLIC")


def downgrade():
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("SELECT public.account_assert_financial_clock_removable()")
    op.execute("DROP TRIGGER billing_financial_clock ON billing_records")
    op.execute("DROP FUNCTION public.account_billing_financial_clock()")
    op.execute("DROP FUNCTION public.account_billing_financial_metadata(jsonb)")
    op.execute("DROP FUNCTION public.account_assert_financial_clock_removable()")
    op.drop_index("ix_billing_financial_due", table_name="billing_records")
    op.drop_column("billing_records", "financial_retain_until")
    op.drop_column("billing_records", "financial_activity_at")
