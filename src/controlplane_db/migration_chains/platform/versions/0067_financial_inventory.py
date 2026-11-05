"""Prime financial source associations before personal owner cleanup."""

from alembic import op

revision = "platform_0067_fin_inventory"
down_revision = "platform_0066_person_references"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE FUNCTION public.account_lock_financial_inventory_schema()
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$ BEGIN
      LOCK TABLE public.account_financial_fence_versions IN ACCESS EXCLUSIVE MODE;
      LOCK TABLE public.identity_retirements, public.account_lifecycles,
        public.account_lifecycle_scopes, public.api_key_owner_closures IN SHARE MODE;
    END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.account_lock_financial_inventory_schema() FROM PUBLIC"
    )
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""CREATE FUNCTION public.account_lock_financial_inventory(
  p_subject text,p_closed_at timestamptz,p_tenant_id uuid DEFAULT NULL)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog SET row_security=off AS $$
BEGIN
  -- Always acquire registry coverage before probing any owner source table.
  LOCK TABLE public.account_financial_fence_versions IN SHARE MODE;
  IF current_setting('transaction_isolation')<>'read committed'
    OR p_subject IS NULL OR length(btrim(p_subject))=0
    OR length(p_subject)>512 OR p_subject LIKE 'apikey:%' OR p_closed_at IS NULL
    OR (SELECT count(*) FROM public.account_financial_fence_versions
        WHERE owner IN ('billing','payment','hypermesh') AND protocol=1)<>3 THEN
    RAISE EXCEPTION 'Native financial inventory authority unavailable' USING ERRCODE='42501';
  END IF;
  IF NOT pg_try_advisory_xact_lock(hashtextextended('identity-retirement:'||p_subject,0)) THEN
    RAISE EXCEPTION 'Financial inventory must retry' USING ERRCODE='40001';
  END IF;
  BEGIN
    PERFORM 1 FROM public.account_lifecycles WHERE subject=p_subject FOR UPDATE NOWAIT;
  EXCEPTION WHEN lock_not_available THEN
    RAISE EXCEPTION 'Financial inventory lifecycle must retry' USING ERRCODE='40001';
  END;
  IF NOT EXISTS (
    SELECT 1 FROM public.account_lifecycles a
    JOIN public.identity_retirements i ON i.subject=a.subject
    WHERE a.subject=p_subject AND a.closed_at=p_closed_at
      AND i.retired_at<=a.closed_at AND a.financial_deleted_at IS NULL
      AND a.state IN ('closed','deleting','deleted')
      AND a.effects @> '{"identity":{"disabled": true},"scope_discovery": true}'::jsonb
      AND jsonb_typeof(a.effects->'scope_tenants')='array'
      AND ((p_tenant_id IS NULL AND jsonb_typeof(a.effects->'platform_profile'->'user_ids')='array')
        OR (p_tenant_id IS NOT NULL
          AND a.effects->'scope_tenants' @> jsonb_build_array(p_tenant_id::text)
          AND EXISTS(SELECT 1 FROM public.account_lifecycle_scopes s
            WHERE s.subject=a.subject AND s.tenant_id=p_tenant_id
              AND s.effects @> '{"profile_inventory_complete": true}'::jsonb)))
  ) THEN
    RAISE EXCEPTION 'Original closed financial inventory scope required' USING ERRCODE='42501';
  END IF;
  -- Preservation holds prevent destruction, never this nondestructive priming.
END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.account_lock_financial_inventory(text,timestamptz,uuid) FROM PUBLIC"
    )
    op.execute("""CREATE FUNCTION public.account_financial_source_bound(
  p_subject text,p_tenant uuid,p_owner text,p_kind text,p_resource text)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
SET search_path=pg_catalog SET row_security=off AS $$
  SELECT EXISTS(SELECT 1 FROM public.account_financial_source_bindings b
    WHERE b.subject=p_subject AND b.tenant_id IS NOT DISTINCT FROM p_tenant
      AND b.owner=p_owner AND b.kind=p_kind AND b.resource=p_resource)
$$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.account_financial_source_bound(text,uuid,text,text,text) FROM PUBLIC"
    )
    op.execute("""CREATE FUNCTION public.account_record_financial_inventory(
  p_subject text,p_closed_at timestamptz,p_tenant uuid,p_owner text)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog SET row_security=off AS $$
BEGIN
  PERFORM public.account_lock_financial_inventory(p_subject,p_closed_at,p_tenant);
  IF p_owner IS NULL OR p_owner NOT IN ('billing','payment','hypermesh') THEN
    RAISE EXCEPTION 'Native inventory owner required' USING ERRCODE='42501';
  END IF;
  IF p_tenant IS NULL THEN
    IF EXISTS(SELECT 1 FROM public.account_lifecycles WHERE subject=p_subject
      AND effects ? 'financial_inventory' AND jsonb_typeof(effects->'financial_inventory')<>'object') THEN
      RAISE EXCEPTION 'Native inventory receipt must be an object' USING ERRCODE='42501';
    END IF;
    UPDATE public.account_lifecycles SET effects=jsonb_set(effects,ARRAY['financial_inventory'],
      coalesce(effects->'financial_inventory','{}'::jsonb)||jsonb_build_object(p_owner,1))
      WHERE subject=p_subject;
  ELSE
    IF EXISTS(SELECT 1 FROM public.account_lifecycle_scopes WHERE subject=p_subject AND tenant_id=p_tenant
      AND effects ? 'financial_inventory' AND jsonb_typeof(effects->'financial_inventory')<>'object') THEN
      RAISE EXCEPTION 'Native inventory receipt must be an object' USING ERRCODE='42501';
    END IF;
    UPDATE public.account_lifecycle_scopes SET effects=jsonb_set(effects,ARRAY['financial_inventory'],
      coalesce(effects->'financial_inventory','{}'::jsonb)||jsonb_build_object(p_owner,1))
      WHERE subject=p_subject AND tenant_id=p_tenant;
  END IF;
END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.account_record_financial_inventory(text,timestamptz,uuid,text) FROM PUBLIC"
    )
    op.execute("""CREATE FUNCTION public.account_prime_billing_financial_sources(
  p_subject text,p_closed_at timestamptz,p_tenant uuid DEFAULT NULL,p_limit integer DEFAULT 100)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog SET row_security=off AS $$
DECLARE source_record record; canonical text[]; processed integer:=0; remaining bigint;
BEGIN
  PERFORM public.account_lock_financial_inventory(p_subject,p_closed_at,p_tenant);
  IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 1000 THEN
    RAISE EXCEPTION 'Bounded inventory batch required' USING ERRCODE='42501';
  END IF;
  -- Selection stays server-side. A caller cursor cannot skip unbound sources.
  FOR source_record IN SELECT b.id,b.user_id,b.metadata FROM public.billing_records b
    WHERE b.tenant_id IS NOT DISTINCT FROM p_tenant
      AND NOT public.account_financial_source_bound(p_subject,p_tenant,'billing','payment',b.id::text)
      AND EXISTS(SELECT 1 FROM public.account_financial_parties(b.user_id,b.metadata->>'actor_sub',
        p_tenant,'billing','payment',b.id::text) p WHERE p.subject=p_subject)
    ORDER BY b.id LIMIT p_limit LOOP
    SELECT array_agg(DISTINCT p.subject) INTO canonical FROM public.account_financial_parties(
      source_record.user_id,source_record.metadata->>'actor_sub',p_tenant,'billing','payment',source_record.id::text) p;
    PERFORM public.account_bind_financial_source(canonical,p_tenant,'billing','payment',source_record.id::text);
    processed:=processed+1;
  END LOOP;
  SELECT count(*) INTO remaining FROM public.billing_records b
    WHERE b.tenant_id IS NOT DISTINCT FROM p_tenant
      AND NOT public.account_financial_source_bound(p_subject,p_tenant,'billing','payment',b.id::text)
      AND EXISTS(SELECT 1 FROM public.account_financial_parties(b.user_id,b.metadata->>'actor_sub',
        p_tenant,'billing','payment',b.id::text) p WHERE p.subject=p_subject);
  IF remaining=0 THEN
    PERFORM public.account_record_financial_inventory(p_subject,p_closed_at,p_tenant,'billing');
  END IF;
  RETURN jsonb_build_object('complete',remaining=0,'processed',processed,'remaining',remaining);
END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.account_prime_billing_financial_sources(text,timestamptz,uuid,integer) FROM PUBLIC"
    )


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute(
        "LOCK TABLE public.identity_retirements, public.account_lifecycles, public.account_lifecycle_scopes, public.api_key_owner_closures IN SHARE MODE"
    )
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("""DO $$ BEGIN
      IF to_regprocedure('public.payment_prime_financial_sources(text,timestamptz,uuid,integer)') IS NOT NULL
        OR to_regprocedure('public.hypermesh_prime_financial_sources(text,timestamptz,uuid,integer)') IS NOT NULL THEN
        RAISE EXCEPTION 'Remove dependent owner inventories before platform inventory';
      END IF;
    END $$""")
    op.execute(
        "DROP FUNCTION public.account_prime_billing_financial_sources(text,timestamptz,uuid,integer)"
    )
    op.execute(
        "DROP FUNCTION public.account_record_financial_inventory(text,timestamptz,uuid,text)"
    )
    op.execute(
        "DROP FUNCTION public.account_financial_source_bound(text,uuid,text,text,text)"
    )
    op.execute(
        "DROP FUNCTION public.account_lock_financial_inventory(text,timestamptz,uuid)"
    )
    op.execute("DROP FUNCTION public.account_lock_financial_inventory_schema()")
