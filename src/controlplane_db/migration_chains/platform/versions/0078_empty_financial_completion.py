"""Finish source-free accounts using fresh installed-owner proofs."""

from alembic import op

revision = "platform_0078_fin_empty"
down_revision = "platform_0077_payer_risk_gc"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""CREATE FUNCTION public.account_native_financial_state(
      p_subject text,p_closed_at timestamptz,p_owner text)
    RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE epoch bigint; remaining bigint;
    BEGIN
      IF p_owner IS NULL OR p_owner NOT IN ('billing','payment','hypermesh') THEN
        RAISE EXCEPTION 'Native financial owner required' USING ERRCODE='42501';
      END IF;
      epoch:=public.account_lock_financial_gc_parties(p_subject,p_closed_at,NULL,ARRAY[p_subject],NULL);
      PERFORM public.account_require_financial_inventory(p_subject,p_closed_at);
      -- Native priming completed before any personal alias was unlinked. Every
      -- installed producer binds later evidence and shares this identity lock.
      -- This authoritative, RLS-independent inventory includes indirect and
      -- unknown ownership; those references are pending, never inferred zero.
      SELECT count(*) INTO remaining FROM public.account_financial_source_bindings
        WHERE subject=p_subject AND owner=p_owner;
      RETURN jsonb_build_object('owner',p_owner,'protocol',1,'epoch',epoch,'remaining',remaining);
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_native_financial_state(text,timestamptz,text) FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.account_billing_financial_state(p_subject text,p_closed_at timestamptz)
    RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE proof jsonb;
    BEGIN
      proof:=public.account_native_financial_state(p_subject,p_closed_at,'billing');
      IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_trigger
        WHERE tgrelid=to_regclass('public.billing_records') AND tgname='billing_financial_epoch'
          AND tgfoid=to_regprocedure('public.account_billing_financial_epoch()')
          AND tgtype=29 AND tgenabled IN ('O','A') AND NOT tgisinternal)
        OR NOT EXISTS(SELECT 1 FROM pg_catalog.pg_trigger
          WHERE tgrelid=to_regclass('public.billing_records') AND tgname='billing_financial_not_truncated'
            AND tgfoid=to_regprocedure('public.account_refuse_financial_truncate()')
            AND tgtype=34 AND tgenabled IN ('O','A') AND NOT tgisinternal) THEN
        RAISE EXCEPTION 'Native billing producer is incomplete' USING ERRCODE='42501';
      END IF;
      RETURN proof;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_billing_financial_state(text,timestamptz) FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.account_finish_source_free_closure(
      p_subject text,p_closed_at timestamptz,p_expected_epoch bigint)
    RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE epoch bigint; result jsonb; owner text; remaining bigint:=0; people uuid[];
      root public.account_lifecycles%ROWTYPE; scope_record record; minimal jsonb; keys jsonb;
    BEGIN
      epoch:=public.account_lock_financial_gc_parties(p_subject,p_closed_at,NULL,ARRAY[p_subject],p_expected_epoch);
      IF p_expected_epoch IS NULL THEN
        RAISE EXCEPTION 'Fresh financial epoch required' USING ERRCODE='42501';
      END IF;
      PERFORM public.account_require_personal_erasure(p_subject,NULL);
      SELECT * INTO STRICT root FROM public.account_lifecycles WHERE subject=p_subject;
      IF root.state<>'deleting' OR root.profile_deleted_at IS NULL
        OR root.effects->'personal_owners_erased' IS DISTINCT FROM 'true'::jsonb
        OR root.effects->'identity_erasure'->'complete' IS DISTINCT FROM 'true'::jsonb THEN
        RAISE EXCEPTION 'Complete personal owner acknowledgements required' USING ERRCODE='42501';
      END IF;
      -- A registry entry alone is not an erasure implementation or a zero proof.
      IF to_regprocedure('public.payment_account_financial_state(text,timestamptz)') IS NULL
        OR to_regprocedure('public.hypermesh_account_financial_state(text,timestamptz)') IS NULL THEN
        RAISE EXCEPTION 'Every native financial owner must supply a current proof' USING ERRCODE='42501';
      END IF;
      FOR owner,result IN SELECT 'billing'::text,public.account_billing_financial_state(p_subject,p_closed_at)
        UNION ALL SELECT 'payment',public.payment_account_financial_state(p_subject,p_closed_at)
        UNION ALL SELECT 'hypermesh',public.hypermesh_account_financial_state(p_subject,p_closed_at) LOOP
        IF result->>'owner' IS DISTINCT FROM owner OR result->'protocol' IS DISTINCT FROM '1'::jsonb
          OR result->'epoch' IS DISTINCT FROM to_jsonb(epoch)
          OR jsonb_typeof(result->'remaining') IS DISTINCT FROM 'number'
          OR (result->>'remaining')::numeric<0 OR (result->>'remaining')::numeric<>trunc((result->>'remaining')::numeric) THEN
          RAISE EXCEPTION 'Current native financial proof required' USING ERRCODE='42501';
        END IF;
        remaining:=remaining+(result->>'remaining')::bigint;
      END LOOP;
      people:=public.account_personal_profile_ids(p_subject,NULL);
      SELECT remaining+count(*) INTO remaining FROM public.crypto_agent_budgets WHERE user_id=ANY(people);
      SELECT remaining+count(*) INTO remaining FROM public.subscription_plans WHERE user_id=ANY(people);
      -- This first completion path handles accounts without renter contracts.
      -- Positive/unknown contract history needs its actual owner erasure stage;
      -- missing current rows must not turn a historical contract into zero.
      FOR scope_record IN SELECT sc.* FROM public.account_lifecycle_scopes sc
        WHERE sc.subject=p_subject ORDER BY sc.tenant_id FOR UPDATE NOWAIT LOOP
        IF jsonb_typeof(scope_record.effects->'hypermesh'->'lease_ids') IS DISTINCT FROM 'array'
          OR jsonb_typeof(scope_record.effects->'api_keys'->'keys') IS DISTINCT FROM 'array' THEN
          RAISE EXCEPTION 'Original native scope authority required' USING ERRCODE='42501';
        END IF;
        IF EXISTS(SELECT 1 FROM jsonb_array_elements(scope_record.effects->'api_keys'->'keys') key
          WHERE key->>'id' IS NULL OR key->>'id' !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') THEN
          RAISE EXCEPTION 'Canonical retired key identities required' USING ERRCODE='42501';
        END IF;
        remaining:=remaining+jsonb_array_length(scope_record.effects->'hypermesh'->'lease_ids');
      END LOOP;
      IF remaining>0 THEN RETURN jsonb_build_object('complete',false,'epoch',epoch,'remaining',remaining); END IF;
      IF public.account_financial_epoch(p_subject,p_closed_at,NULL,epoch)<>epoch THEN
        RAISE EXCEPTION 'Financial evidence changed; retry' USING ERRCODE='40001';
      END IF;
      -- Keep only minimal universal retirement aliases and admission fences.
      -- User/key UUIDs identify retired principals, not payment/source records.
      -- Remove original resource IDs, financial progress and cleanup counters.
      FOR scope_record IN SELECT sc.* FROM public.account_lifecycle_scopes sc
        WHERE sc.subject=p_subject ORDER BY sc.tenant_id FOR UPDATE NOWAIT LOOP
        SELECT coalesce(jsonb_object_agg(key,value),'{}'::jsonb) INTO minimal
          FROM jsonb_each(scope_record.effects) WHERE jsonb_typeof(value)='boolean';
        SELECT coalesce(jsonb_agg(jsonb_strip_nulls(jsonb_build_object(
          'id',key->>'id','fingerprint',key->>'fingerprint'))),'[]'::jsonb) INTO keys
          FROM jsonb_array_elements(scope_record.effects->'api_keys'->'keys') key;
        UPDATE public.account_lifecycle_scopes SET effects=minimal||jsonb_build_object(
          'api_keys',jsonb_build_object('keys',keys),'hypermesh',jsonb_build_object('lease_ids','[]'::jsonb),
          'financial_inventory',scope_record.effects->'financial_inventory')
          WHERE subject=p_subject AND tenant_id=scope_record.tenant_id;
      END LOOP;
      SELECT coalesce(jsonb_object_agg(key,value),'{}'::jsonb) INTO minimal
        FROM jsonb_each(root.effects) WHERE jsonb_typeof(value)='boolean';
      minimal:=minimal||jsonb_build_object('processor_version',1,'identity',root.effects->'identity',
        'identity_erasure',jsonb_build_object('complete',true),'scope_tenants',root.effects->'scope_tenants',
        'platform_profile',jsonb_build_object('user_ids',root.effects->'platform_profile'->'user_ids'),
        'financial_inventory',root.effects->'financial_inventory');
      UPDATE public.account_lifecycles SET effects=minimal,state='deleted',financial_deleted_at=transaction_timestamp(),
        last_error=NULL,claim_id=NULL,claim_until=NULL WHERE subject=p_subject;
      RETURN jsonb_build_object('complete',true,'epoch',epoch,'remaining',0);
    EXCEPTION WHEN lock_not_available THEN
      RAISE EXCEPTION 'Source-free completion must retry' USING ERRCODE='40001';
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_finish_source_free_closure(text,timestamptz,bigint) FROM PUBLIC")


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("""DO $$ BEGIN IF to_regprocedure('public.payment_account_financial_state(text,timestamptz)') IS NOT NULL
      OR to_regprocedure('public.hypermesh_account_financial_state(text,timestamptz)') IS NOT NULL THEN
      RAISE EXCEPTION 'Remove owner financial state functions before their platform support'; END IF; END $$""")
    op.execute("DROP FUNCTION public.account_finish_source_free_closure(text,timestamptz,bigint)")
    op.execute("DROP FUNCTION public.account_billing_financial_state(text,timestamptz)")
    op.execute("DROP FUNCTION public.account_native_financial_state(text,timestamptz,text)")
