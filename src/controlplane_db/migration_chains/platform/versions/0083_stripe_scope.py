"""Require original billing provenance for leases and nested Stripe metadata."""
from alembic import op
import sqlalchemy as sa

revision = "platform_0083_stripe_scope"
down_revision = "platform_0082_stripe_mode"
branch_labels = None
depends_on = None
_SIGNATURE = "public.account_test_check_row(text,jsonb)"
_BACKUP = "platform_0083_stripe_scope:" + _SIGNATURE


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""CREATE FUNCTION public.account_test_stripe_metadata(p_data jsonb) RETURNS boolean
      LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET row_security=off AS $$
      DECLARE item record; value jsonb;
      BEGIN
        IF jsonb_typeof(p_data)='string' THEN RETURN left(lower(p_data#>>'{}'),6)='stripe';
        ELSIF jsonb_typeof(p_data)='object' THEN
          FOR item IN SELECT * FROM jsonb_each(p_data) LOOP
            IF left(lower(item.key),6)='stripe' OR public.account_test_stripe_metadata(item.value) THEN RETURN true; END IF;
          END LOOP;
        ELSIF jsonb_typeof(p_data)='array' THEN
          FOR value IN SELECT * FROM jsonb_array_elements(p_data) LOOP
            IF public.account_test_stripe_metadata(value) THEN RETURN true; END IF;
          END LOOP;
        END IF;
        RETURN false;
      END $$;
      REVOKE ALL ON FUNCTION public.account_test_stripe_metadata(jsonb) FROM PUBLIC;
    """)
    op.execute("ALTER TABLE public.account_test_policy_originals NO FORCE ROW LEVEL SECURITY")
    connection=op.get_bind()
    target = ('public.account_test_check_row_pre0083(text,jsonb)'
              if connection.scalar(sa.text("SELECT to_regprocedure('public.account_test_check_row_pre0083(text,jsonb)') IS NOT NULL"))
              else _SIGNATURE)
    definition=connection.scalar(sa.text("SELECT pg_get_functiondef(CAST(:s AS regprocedure))"),{'s':target})
    previous="BEGIN\n  IF p_name='billing_records' AND (\n      p_data->'stripe_livemode'='true'::jsonb OR (\n        (coalesce(p_data->>'stripe_customer_id',p_data->>'stripe_subscription_id',p_data->>'stripe_session_id',p_data->>'product_id',p_data->>'price_id') IS NOT NULL\n          OR p_data->>'payment_type' LIKE 'stripe%'\n          OR EXISTS(SELECT 1 FROM jsonb_object_keys(CASE WHEN jsonb_typeof(p_data->'metadata')='object' THEN p_data->'metadata' ELSE '{}'::jsonb END) k WHERE left(k,6)='stripe'))\n        AND p_data->'stripe_livemode' IS DISTINCT FROM 'false'::jsonb)) THEN\n    RAISE EXCEPTION 'Immutable Stripe sandbox provenance required' USING ERRCODE='42501'; END IF;\n  IF (p_data ? 'livemode'"
    replacement="BEGIN\n  IF p_name='billing_records' AND (\n      p_data->'stripe_livemode'='true'::jsonb OR (\n        (coalesce(p_data->>'stripe_customer_id',p_data->>'stripe_subscription_id',p_data->>'stripe_session_id',p_data->>'product_id',p_data->>'price_id') IS NOT NULL\n          OR lower(p_data->>'payment_type') LIKE 'stripe%'\n          OR public.account_test_stripe_metadata(p_data->'metadata'))\n        AND p_data->'stripe_livemode' IS DISTINCT FROM 'false'::jsonb)) THEN\n    RAISE EXCEPTION 'Immutable Stripe sandbox provenance required' USING ERRCODE='42501'; END IF;\n  IF p_name='hypermesh_leases' THEN\n    IF p_data->>'billing_record_id' IS NOT NULL THEN\n      SELECT to_jsonb(b) INTO billing FROM public.billing_records b\n        WHERE b.id=(p_data->>'billing_record_id')::uuid\n          AND b.tenant_id IS NOT DISTINCT FROM (p_data->>'tenant_id')::uuid;\n      IF billing IS NULL OR (p_data->>'stripe_session_id' IS NOT NULL\n        AND p_data->>'stripe_session_id' IS DISTINCT FROM billing->>'stripe_session_id') THEN\n        RAISE EXCEPTION 'Original Stripe lease sandbox provenance required' USING ERRCODE='42501'; END IF;\n      BEGIN\n        PERFORM public.account_test_check_row('billing_records',billing);\n      EXCEPTION WHEN insufficient_privilege THEN\n        RAISE EXCEPTION 'Original Stripe lease sandbox provenance required' USING ERRCODE='42501';\n      END;\n    ELSIF p_data->>'stripe_session_id' IS NOT NULL THEN\n      RAISE EXCEPTION 'Original Stripe lease sandbox provenance required' USING ERRCODE='42501'; END IF;\n  END IF;\n  IF (p_data ? 'livemode'"
    if definition.count(previous)!=1 or definition.count('DECLARE mode boolean;')!=1:
        raise RuntimeError("Expected original Stripe billing provenance guard")
    connection.execute(sa.text('INSERT INTO public.account_test_policy_originals VALUES(:s,:d)'),{'s':_BACKUP,'d':definition})
    definition=definition.replace('DECLARE mode boolean;','DECLARE mode boolean; billing jsonb;').replace(previous,replacement)
    connection.exec_driver_sql(definition,execution_options={'no_parameters':True})
    op.execute("ALTER TABLE public.account_test_policy_originals FORCE ROW LEVEL SECURITY")


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""DO $$ BEGIN IF public.account_test_data_enabled() THEN
      RAISE EXCEPTION 'Disable TEST policy before removing Stripe scope protection'; END IF; END $$""")
    op.execute("ALTER TABLE public.account_test_policy_originals NO FORCE ROW LEVEL SECURITY")
    connection=op.get_bind()
    definition=connection.scalar(sa.text('SELECT definition FROM public.account_test_policy_originals WHERE signature=:s'),{'s':_BACKUP})
    if not definition:raise RuntimeError('Original Stripe billing guard required')
    target = ('account_test_check_row_pre0083'
              if connection.scalar(sa.text("SELECT to_regprocedure('public.account_test_check_row_pre0083(text,jsonb)') IS NOT NULL"))
              else 'account_test_check_row')
    for name in ('account_test_check_row_pre0083','account_test_check_row'):
        header='CREATE OR REPLACE FUNCTION public.'+name+'('
        if definition.startswith(header):
            definition=definition.replace(header,'CREATE OR REPLACE FUNCTION public.'+target+'(',1)
            break
    else:raise RuntimeError('Original Stripe guard declaration required')
    connection.exec_driver_sql(definition,execution_options={'no_parameters':True})
    connection.execute(sa.text('DELETE FROM public.account_test_policy_originals WHERE signature=:s'),{'s':_BACKUP})
    op.execute('DROP FUNCTION public.account_test_stripe_metadata(jsonb)')
    op.execute("ALTER TABLE public.account_test_policy_originals FORCE ROW LEVEL SECURITY")
