"""Prime native payment source associations before personal cleanup."""

from alembic import op

revision = "payment_service_0077_fin_inv"
down_revision = "payment_service_0076_financial"
branch_labels = None
depends_on = None


def upgrade():
    # Require the platform inventory schema and serialize capability changes.
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""CREATE FUNCTION public.payment_financial_inventory_parties(p_table text,p_source jsonb)
RETURNS TABLE(subject text) LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog SET row_security=off AS $$
DECLARE native_tenant uuid; actor text; source_id text; billing uuid; parent_source jsonb;
BEGIN
  IF p_table NOT IN ('host_payout_addresses','connect_recipient_accounts','billing_tax_orders',
    'billing_tax_calculations','connect_bank_approvals','connect_reversal_exposure_observations',
    'connect_control_proofs','connect_access_states','connect_access_grants','connect_access_results',
    'payer_mismatch_accounts') OR p_table IS NULL THEN
    RAISE EXCEPTION 'Native payment inventory source required' USING ERRCODE='42501';
  END IF;
  native_tenant:=(p_source->>'tenant_id')::uuid;
  actor:=coalesce(p_source->>'owner_sub',p_source->>'verified_by_sub',p_source->>'initiated_by_sub',
    p_source->'lifecycle'->'owner'->>'subject',p_source->'adoption'->>'owner_sub');
  source_id:=coalesce(CASE WHEN p_table='host_payout_addresses' THEN
    (p_source->>'host_org_id')||':'||(p_source->>'chain_id') END,p_source->>'id',p_source->>'grant_id',
    p_source->>'revision_id',p_source->>'account_key',p_source->>'host_org_id');
  billing:=(p_source->>'billing_record_id')::uuid;
  IF p_table='billing_tax_calculations' THEN
    SELECT o.billing_record_id INTO billing FROM public.billing_tax_orders o
      WHERE o.revision_id=(p_source->>'revision_id')::uuid AND o.tenant_id=native_tenant;
  ELSIF p_table='connect_access_results' THEN
    SELECT g.owner_sub INTO actor FROM public.connect_access_grants g
      WHERE g.id=(p_source->>'grant_id')::uuid AND g.tenant_id=native_tenant;
  END IF;
  RETURN QUERY SELECT p.subject FROM public.account_financial_parties(NULL,actor,native_tenant,
    'payment',p_table,source_id,CASE WHEN p_table='payer_mismatch_accounts' THEN p_source->>'account_key' END) p;
  IF billing IS NOT NULL THEN
    parent_source:=public.account_billing_financial_source(billing,native_tenant);
    RETURN QUERY SELECT p.subject FROM public.account_financial_parties(
      (parent_source->>'user_id')::uuid,parent_source->'metadata'->>'actor_sub',native_tenant,
      'billing','payment',billing::text) p;
  END IF;
END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.payment_financial_inventory_parties(text,jsonb) FROM PUBLIC"
    )
    op.execute("""CREATE FUNCTION public.payment_prime_financial_sources(
  p_subject text,p_closed_at timestamptz,p_tenant uuid,p_limit integer DEFAULT 100)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog SET row_security=off AS $$
DECLARE source_record record; canonical text[]; processed integer:=0; remaining bigint;
BEGIN
  PERFORM public.account_lock_financial_inventory(p_subject,p_closed_at,p_tenant);
  IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 1000 THEN
    RAISE EXCEPTION 'Bounded inventory batch required' USING ERRCODE='42501';
  END IF;
  FOR source_record IN SELECT n.kind,n.source,coalesce(CASE WHEN n.kind='host_payout_addresses' THEN (n.source->>'host_org_id')||':'||(n.source->>'chain_id') END,n.source->>'id',n.source->>'grant_id',n.source->>'revision_id',n.source->>'account_key',n.source->>'host_org_id') AS resource FROM (
    SELECT 'host_payout_addresses'::text AS kind,to_jsonb(r) AS source FROM public.host_payout_addresses r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'connect_recipient_accounts'::text AS kind,to_jsonb(r) AS source FROM public.connect_recipient_accounts r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'billing_tax_orders'::text AS kind,to_jsonb(r) AS source FROM public.billing_tax_orders r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'billing_tax_calculations'::text AS kind,to_jsonb(r) AS source FROM public.billing_tax_calculations r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'connect_bank_approvals'::text AS kind,to_jsonb(r) AS source FROM public.connect_bank_approvals r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'connect_reversal_exposure_observations'::text AS kind,to_jsonb(r) AS source FROM public.connect_reversal_exposure_observations r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'connect_control_proofs'::text AS kind,to_jsonb(r) AS source FROM public.connect_control_proofs r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'connect_access_states'::text AS kind,to_jsonb(r) AS source FROM public.connect_access_states r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'connect_access_grants'::text AS kind,to_jsonb(r) AS source FROM public.connect_access_grants r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'connect_access_results'::text AS kind,to_jsonb(r) AS source FROM public.connect_access_results r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'payer_mismatch_accounts'::text AS kind,to_jsonb(r) AS source FROM public.payer_mismatch_accounts r WHERE p_tenant IS NULL
  ) n WHERE NOT public.account_financial_source_bound(p_subject,p_tenant,'payment',n.kind,coalesce(CASE WHEN n.kind='host_payout_addresses' THEN (n.source->>'host_org_id')||':'||(n.source->>'chain_id') END,n.source->>'id',n.source->>'grant_id',n.source->>'revision_id',n.source->>'account_key',n.source->>'host_org_id'))
      AND EXISTS(SELECT 1 FROM public.payment_financial_inventory_parties(n.kind,n.source) p WHERE p.subject=p_subject) ORDER BY n.kind,coalesce(CASE WHEN n.kind='host_payout_addresses' THEN (n.source->>'host_org_id')||':'||(n.source->>'chain_id') END,n.source->>'id',n.source->>'grant_id',n.source->>'revision_id',n.source->>'account_key',n.source->>'host_org_id') LIMIT p_limit LOOP
    SELECT array_agg(DISTINCT p.subject) INTO canonical
      FROM public.payment_financial_inventory_parties(source_record.kind,source_record.source) p;
    PERFORM public.account_bind_financial_source(canonical,p_tenant,'payment',source_record.kind,source_record.resource);
    processed:=processed+1;
  END LOOP;
  SELECT count(*) INTO remaining FROM (
    SELECT 'host_payout_addresses'::text AS kind,to_jsonb(r) AS source FROM public.host_payout_addresses r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'connect_recipient_accounts'::text AS kind,to_jsonb(r) AS source FROM public.connect_recipient_accounts r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'billing_tax_orders'::text AS kind,to_jsonb(r) AS source FROM public.billing_tax_orders r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'billing_tax_calculations'::text AS kind,to_jsonb(r) AS source FROM public.billing_tax_calculations r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'connect_bank_approvals'::text AS kind,to_jsonb(r) AS source FROM public.connect_bank_approvals r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'connect_reversal_exposure_observations'::text AS kind,to_jsonb(r) AS source FROM public.connect_reversal_exposure_observations r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'connect_control_proofs'::text AS kind,to_jsonb(r) AS source FROM public.connect_control_proofs r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'connect_access_states'::text AS kind,to_jsonb(r) AS source FROM public.connect_access_states r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'connect_access_grants'::text AS kind,to_jsonb(r) AS source FROM public.connect_access_grants r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'connect_access_results'::text AS kind,to_jsonb(r) AS source FROM public.connect_access_results r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'payer_mismatch_accounts'::text AS kind,to_jsonb(r) AS source FROM public.payer_mismatch_accounts r WHERE p_tenant IS NULL
  ) n WHERE NOT public.account_financial_source_bound(p_subject,p_tenant,'payment',n.kind,coalesce(CASE WHEN n.kind='host_payout_addresses' THEN (n.source->>'host_org_id')||':'||(n.source->>'chain_id') END,n.source->>'id',n.source->>'grant_id',n.source->>'revision_id',n.source->>'account_key',n.source->>'host_org_id'))
      AND EXISTS(SELECT 1 FROM public.payment_financial_inventory_parties(n.kind,n.source) p WHERE p.subject=p_subject);
  IF remaining=0 THEN
    PERFORM public.account_record_financial_inventory(p_subject,p_closed_at,p_tenant,'payment');
  END IF;
  RETURN jsonb_build_object('complete',remaining=0,'processed',processed,'remaining',remaining);
END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.payment_prime_financial_sources(text,timestamptz,uuid,integer) FROM PUBLIC"
    )


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute(
        "DROP FUNCTION public.payment_prime_financial_sources(text,timestamptz,uuid,integer)"
    )
    op.execute("DROP FUNCTION public.payment_financial_inventory_parties(text,jsonb)")
