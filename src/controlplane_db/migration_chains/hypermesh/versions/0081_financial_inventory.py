"""Prime native hypermesh source associations before personal cleanup."""

from alembic import op

revision = "hypermesh_0081_fin_inventory"
down_revision = "hypermesh_0080_financial"
branch_labels = None
depends_on = None


def upgrade():
    # Require the platform inventory schema and serialize capability changes.
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""CREATE FUNCTION public.hypermesh_prime_financial_sources(
  p_subject text,p_closed_at timestamptz,p_tenant uuid,p_limit integer DEFAULT 100)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog SET row_security=off AS $$
DECLARE source_record record; canonical text[]; processed integer:=0; remaining bigint;
BEGIN
  PERFORM public.account_lock_financial_inventory(p_subject,p_closed_at,p_tenant);
  IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 1000 THEN
    RAISE EXCEPTION 'Bounded inventory batch required' USING ERRCODE='42501';
  END IF;
  FOR source_record IN SELECT n.kind,n.source,coalesce(n.source->>'id',n.source->>'order_id',n.source->>'lease_id',n.source->>'organization_id') AS resource FROM (
    SELECT 'hypermesh_leases'::text AS kind,to_jsonb(r) AS source FROM public.hypermesh_leases r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'hypermesh_payouts'::text AS kind,to_jsonb(r) AS source FROM public.hypermesh_payouts r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'hypermesh_orders'::text AS kind,to_jsonb(r) AS source FROM public.hypermesh_orders r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'hypermesh_fills'::text AS kind,to_jsonb(r) AS source FROM public.hypermesh_fills r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'hypermesh_jobs'::text AS kind,to_jsonb(r) AS source FROM public.hypermesh_jobs r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'hypermesh_tunnels'::text AS kind,to_jsonb(r) AS source FROM public.hypermesh_tunnels r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'hypermesh_tickets'::text AS kind,to_jsonb(r) AS source FROM public.hypermesh_tickets r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'host_organization_bindings'::text AS kind,to_jsonb(r) AS source FROM public.host_organization_bindings r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
  ) n WHERE NOT public.account_financial_source_bound(p_subject,p_tenant,'hypermesh',n.kind,coalesce(n.source->>'id',n.source->>'order_id',n.source->>'lease_id',n.source->>'organization_id'))
      AND EXISTS(SELECT 1 FROM public.hypermesh_financial_parties(n.kind,n.source) p WHERE p.subject=p_subject) ORDER BY n.kind,coalesce(n.source->>'id',n.source->>'order_id',n.source->>'lease_id',n.source->>'organization_id') LIMIT p_limit LOOP
    SELECT array_agg(DISTINCT p.subject) INTO canonical
      FROM public.hypermesh_financial_parties(source_record.kind,source_record.source) p;
    PERFORM public.account_bind_financial_source(canonical,p_tenant,'hypermesh',source_record.kind,source_record.resource);
    processed:=processed+1;
  END LOOP;
  SELECT count(*) INTO remaining FROM (
    SELECT 'hypermesh_leases'::text AS kind,to_jsonb(r) AS source FROM public.hypermesh_leases r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'hypermesh_payouts'::text AS kind,to_jsonb(r) AS source FROM public.hypermesh_payouts r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'hypermesh_orders'::text AS kind,to_jsonb(r) AS source FROM public.hypermesh_orders r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'hypermesh_fills'::text AS kind,to_jsonb(r) AS source FROM public.hypermesh_fills r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'hypermesh_jobs'::text AS kind,to_jsonb(r) AS source FROM public.hypermesh_jobs r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'hypermesh_tunnels'::text AS kind,to_jsonb(r) AS source FROM public.hypermesh_tunnels r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'hypermesh_tickets'::text AS kind,to_jsonb(r) AS source FROM public.hypermesh_tickets r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
    UNION ALL
    SELECT 'host_organization_bindings'::text AS kind,to_jsonb(r) AS source FROM public.host_organization_bindings r WHERE r.tenant_id IS NOT DISTINCT FROM p_tenant
  ) n WHERE NOT public.account_financial_source_bound(p_subject,p_tenant,'hypermesh',n.kind,coalesce(n.source->>'id',n.source->>'order_id',n.source->>'lease_id',n.source->>'organization_id'))
      AND EXISTS(SELECT 1 FROM public.hypermesh_financial_parties(n.kind,n.source) p WHERE p.subject=p_subject);
  IF remaining=0 THEN
    PERFORM public.account_record_financial_inventory(p_subject,p_closed_at,p_tenant,'hypermesh');
  END IF;
  RETURN jsonb_build_object('complete',remaining=0,'processed',processed,'remaining',remaining);
END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.hypermesh_prime_financial_sources(text,timestamptz,uuid,integer) FROM PUBLIC"
    )


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute(
        "DROP FUNCTION public.hypermesh_prime_financial_sources(text,timestamptz,uuid,integer)"
    )
