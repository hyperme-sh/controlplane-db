"""Check nested Stripe markers and original lease billing provenance."""
from alembic import op

revision = 'platform_0083_stripe_ancestry'
down_revision = 'platform_0082_stripe_mode'
branch_labels = None
depends_on = None


def upgrade():
    op.execute('SELECT public.account_lock_financial_inventory_schema()')
    op.execute('ALTER FUNCTION public.account_test_check_row(text,jsonb) RENAME TO account_test_check_row_pre0083')
    op.execute("""CREATE FUNCTION public.account_test_check_row(p_name text,p_data jsonb) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,pg_temp SET row_security=off AS $$
    DECLARE billing jsonb; stripe_marker boolean;
    BEGIN
      PERFORM public.account_test_check_row_pre0083(p_name,p_data);
      IF p_name='billing_records' THEN
        WITH RECURSIVE nodes(k,v) AS (
          SELECT ''::text,coalesce(p_data->'metadata','{}'::jsonb)
          UNION ALL
          SELECT child.k,child.v FROM nodes n CROSS JOIN LATERAL (
            SELECT key AS k,value AS v FROM jsonb_each(CASE WHEN jsonb_typeof(n.v)='object' THEN n.v ELSE '{}'::jsonb END)
            UNION ALL
            SELECT '',value FROM jsonb_array_elements(CASE WHEN jsonb_typeof(n.v)='array' THEN n.v ELSE '[]'::jsonb END)
          ) child
        ) SELECT EXISTS(SELECT 1 FROM nodes WHERE left(lower(k),6)='stripe'
          OR (jsonb_typeof(v)='string' AND left(lower(v#>>'{}'),6)='stripe')) INTO stripe_marker;
        IF stripe_marker AND p_data->'stripe_livemode' IS DISTINCT FROM 'false'::jsonb THEN
          RAISE EXCEPTION 'Immutable Stripe sandbox provenance required' USING ERRCODE='42501'; END IF;
      ELSIF p_name='hypermesh_leases' AND p_data->>'stripe_session_id' IS NOT NULL THEN
        SELECT to_jsonb(b) INTO billing FROM public.billing_records b
          WHERE b.id=(p_data->>'billing_record_id')::uuid
            AND b.tenant_id IS NOT DISTINCT FROM (p_data->>'tenant_id')::uuid
            AND b.stripe_session_id=p_data->>'stripe_session_id';
        IF billing IS NULL OR billing->'stripe_livemode' IS DISTINCT FROM 'false'::jsonb THEN
          RAISE EXCEPTION 'Original Stripe lease sandbox provenance required' USING ERRCODE='42501'; END IF;
        PERFORM public.account_test_check_row('billing_records',billing);
      END IF;
    END $$;
    REVOKE ALL ON FUNCTION public.account_test_check_row(text,jsonb) FROM PUBLIC;
    DO $$ DECLARE item record; BEGIN
      FOR item IN SELECT DISTINCT a.grantee,p.proowner FROM pg_proc p,
        LATERAL aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
        WHERE p.oid='public.account_test_check_row_pre0083(text,jsonb)'::regprocedure
          AND a.grantee<>p.proowner AND a.grantee<>0
      LOOP
        EXECUTE format('GRANT EXECUTE ON FUNCTION public.account_test_check_row(text,jsonb) TO %I',pg_get_userbyid(item.grantee));
        EXECUTE format('REVOKE ALL ON FUNCTION public.account_test_check_row_pre0083(text,jsonb) FROM %I',pg_get_userbyid(item.grantee));
      END LOOP;
    END $$;
    REVOKE ALL ON FUNCTION public.account_test_check_row_pre0083(text,jsonb) FROM PUBLIC;
    """)


def downgrade():
    op.execute('SELECT public.account_lock_financial_inventory_schema()')
    op.execute("""DO $$ BEGIN IF public.account_test_data_enabled() THEN
      RAISE EXCEPTION 'Disable TEST policy before removing Stripe ancestry protection'; END IF; END $$""")
    op.execute('DROP FUNCTION public.account_test_check_row(text,jsonb)')
    op.execute('ALTER FUNCTION public.account_test_check_row_pre0083(text,jsonb) RENAME TO account_test_check_row')
