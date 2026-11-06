"""Keep immutable Stripe mode provenance separate from TEST database intent."""
from alembic import op
import sqlalchemy as sa

revision = "platform_0082_stripe_mode"
down_revision = "platform_0081_test_authority"
branch_labels = None
depends_on = None
_SIGNATURE = "public.account_test_check_row(text,jsonb)"


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("ALTER TABLE public.billing_records ADD COLUMN stripe_livemode boolean")
    op.execute("""CREATE FUNCTION public.account_billing_stripe_mode_immutable() RETURNS trigger
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET row_security=off AS $$
      BEGIN
        IF TG_OP='UPDATE' AND OLD.stripe_livemode IS NOT NULL
          AND NEW.stripe_livemode IS DISTINCT FROM OLD.stripe_livemode THEN
          RAISE EXCEPTION 'Stripe billing mode is immutable' USING ERRCODE='42501'; END IF;
        RETURN NEW;
      END $$;
      REVOKE ALL ON FUNCTION public.account_billing_stripe_mode_immutable() FROM PUBLIC;
      CREATE TRIGGER billing_stripe_mode_immutable BEFORE INSERT OR UPDATE ON public.billing_records
        FOR EACH ROW EXECUTE FUNCTION public.account_billing_stripe_mode_immutable();
    """)
    connection = op.get_bind()
    definition = connection.scalar(sa.text("SELECT pg_get_functiondef(CAST(:s AS regprocedure))"), {"s":_SIGNATURE})
    anchor = "BEGIN\n  IF (p_data ? 'livemode'"
    if definition.count(anchor)!=1:
        raise RuntimeError("Expected original TEST row provenance guard")
    connection.execute(sa.text("INSERT INTO public.account_test_policy_originals VALUES(:s,:d)"), {"s":_SIGNATURE,"d":definition})
    guard = """BEGIN
  IF p_name='billing_records' AND (
      p_data->'stripe_livemode'='true'::jsonb OR (
        (coalesce(p_data->>'stripe_customer_id',p_data->>'stripe_subscription_id',p_data->>'stripe_session_id',p_data->>'product_id',p_data->>'price_id') IS NOT NULL
          OR EXISTS(SELECT 1 FROM jsonb_object_keys(coalesce(p_data->'metadata','{}'::jsonb)) k WHERE left(k,7)='stripe_'))
        AND p_data->'stripe_livemode' IS DISTINCT FROM 'false'::jsonb)) THEN
    RAISE EXCEPTION 'Authoritative sandbox Stripe billing provenance required' USING ERRCODE='42501'; END IF;
  IF (p_data ? 'livemode'"""
    connection.exec_driver_sql(definition.replace(anchor,guard),execution_options={"no_parameters":True})


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("LOCK TABLE public.billing_records IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM public.billing_records WHERE stripe_livemode IS NOT NULL) THEN
        RAISE EXCEPTION 'Preserve recorded Stripe mode provenance before downgrade'; END IF;
      IF public.account_test_data_enabled() THEN
        RAISE EXCEPTION 'Disable TEST policy before removing Stripe mode protection'; END IF;
    END $$""")
    connection=op.get_bind()
    definition=connection.scalar(sa.text("SELECT definition FROM public.account_test_policy_originals WHERE signature=:s"),{"s":_SIGNATURE})
    if not definition:raise RuntimeError("Original TEST row guard required")
    connection.exec_driver_sql(definition,execution_options={"no_parameters":True})
    connection.execute(sa.text("DELETE FROM public.account_test_policy_originals WHERE signature=:s"),{"s":_SIGNATURE})
    op.execute("DROP TRIGGER billing_stripe_mode_immutable ON public.billing_records")
    op.execute("DROP FUNCTION public.account_billing_stripe_mode_immutable()")
    op.execute("ALTER TABLE public.billing_records DROP COLUMN stripe_livemode")
