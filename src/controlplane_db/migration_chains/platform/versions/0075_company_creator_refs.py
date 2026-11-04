"""Unlink known personal creators while preserving company assets and routing."""

from alembic import op

revision = "platform_0075_creator_refs"
down_revision = "platform_0074_paid_creator"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""CREATE FUNCTION public.account_personal_profile_ids(p_subject text,p_tenant uuid)
    RETURNS uuid[] LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE result uuid[]; profile_ids jsonb;
    BEGIN
      PERFORM public.account_require_personal_erasure(p_subject,p_tenant);
      SELECT effects->'platform_profile'->'user_ids' INTO profile_ids FROM public.account_lifecycles WHERE subject=p_subject;
      IF jsonb_typeof(profile_ids) IS DISTINCT FROM 'array' OR EXISTS(
        SELECT 1 FROM public.account_lifecycle_scopes sc JOIN public.account_lifecycles a ON a.subject=sc.subject
        WHERE sc.subject=p_subject AND a.effects->'scope_tenants' @> jsonb_build_array(sc.tenant_id::text)
          AND jsonb_typeof(sc.user_ids) IS DISTINCT FROM 'array') THEN
        RAISE EXCEPTION 'Original profile references required' USING ERRCODE='42501';
      END IF;
      SELECT coalesce(jsonb_agg(value),'[]'::jsonb) INTO profile_ids FROM (SELECT value FROM (
        SELECT value FROM jsonb_array_elements_text(profile_ids) value
        UNION ALL
        SELECT jsonb_array_elements_text(sc.user_ids) AS value FROM public.account_lifecycle_scopes sc
          JOIN public.account_lifecycles a ON a.subject=sc.subject
          WHERE sc.subject=p_subject AND a.effects->'scope_tenants' @> jsonb_build_array(sc.tenant_id::text)
      ) original LIMIT 100001) bounded;
      IF jsonb_array_length(profile_ids)>100000 OR EXISTS(SELECT 1 FROM jsonb_array_elements_text(profile_ids) value
        WHERE value IS NULL OR value !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') THEN
        RAISE EXCEPTION 'Canonical original profile references required' USING ERRCODE='42501';
      END IF;
      SELECT coalesce(array_agg(DISTINCT value::uuid),ARRAY[]::uuid[]) INTO result FROM jsonb_array_elements_text(profile_ids) value;
      RETURN result;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_personal_profile_ids(text,uuid) FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.account_erase_personal_company_creators(
      p_subject text,p_closed_at timestamptz,p_tenant uuid,p_limit integer DEFAULT 100)
    RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE people uuid[]; item record; processed integer:=0; remaining bigint; retained bigint;
      marker jsonb;
    BEGIN
      PERFORM public.account_lock_financial_inventory(p_subject,p_closed_at,p_tenant);
      people:=public.account_personal_profile_ids(p_subject,p_tenant);
      IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 1000 THEN
        RAISE EXCEPTION 'Bounded creator cleanup required' USING ERRCODE='42501';
      END IF;
      FOR item IN SELECT id FROM public.crypto_agent_budgets WHERE tenant_id IS NOT DISTINCT FROM p_tenant
        AND user_id=ANY(people) AND label IS DISTINCT FROM 'fake-usdc'
        ORDER BY id LIMIT p_limit FOR UPDATE NOWAIT LOOP
        UPDATE public.crypto_agent_budgets SET user_id=NULL WHERE id=item.id;
        processed:=processed+1;
      END LOOP;
      FOR item IN SELECT id FROM public.subscription_plans WHERE tenant_id IS NOT DISTINCT FROM p_tenant
        AND user_id=ANY(people) ORDER BY id LIMIT p_limit FOR UPDATE NOWAIT LOOP
        UPDATE public.subscription_plans SET user_id=NULL WHERE id=item.id;
        processed:=processed+1;
      END LOOP;
      SELECT (SELECT count(*) FROM public.crypto_agent_budgets WHERE tenant_id IS NOT DISTINCT FROM p_tenant
          AND user_id=ANY(people) AND label IS DISTINCT FROM 'fake-usdc')
        +(SELECT count(*) FROM public.subscription_plans WHERE tenant_id IS NOT DISTINCT FROM p_tenant
          AND user_id=ANY(people)) INTO remaining;
      SELECT count(*) INTO retained FROM public.crypto_agent_budgets WHERE tenant_id IS NOT DISTINCT FROM p_tenant
        AND user_id=ANY(people) AND label='fake-usdc';
      -- Legacy burns still route through this minimal UUID. Never erase a
      -- routing dependency or mutate its wallet, allocation, ceiling or label.
      marker:=jsonb_build_object('retained_budget_references',retained);
      IF remaining=0 THEN marker:=marker||'{"company_creator_refs_unlinked": true}'::jsonb; END IF;
      IF p_tenant IS NULL THEN UPDATE public.account_lifecycles SET effects=effects||marker WHERE subject=p_subject;
      ELSE UPDATE public.account_lifecycle_scopes SET effects=effects||marker WHERE subject=p_subject AND tenant_id=p_tenant; END IF;
      RETURN jsonb_build_object('complete',remaining=0,'processed',processed,'remaining',remaining);
    EXCEPTION WHEN lock_not_available THEN
      RAISE EXCEPTION 'Creator cleanup must retry' USING ERRCODE='40001';
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_erase_personal_company_creators(text,timestamptz,uuid,integer) FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.account_budget_creator_fence()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE candidate text;
    BEGIN
      IF NEW.user_id IS NULL OR NEW.user_id IS DISTINCT FROM OLD.user_id
        OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id OR NEW.label='fake-usdc' THEN RETURN NEW; END IF;
      IF current_setting('transaction_isolation')<>'read committed' THEN
        RAISE EXCEPTION 'Creator maintenance requires READ COMMITTED' USING ERRCODE='42501';
      END IF;
      BEGIN
        LOCK TABLE public.account_financial_fence_versions IN SHARE MODE NOWAIT;
      EXCEPTION WHEN lock_not_available THEN
        RAISE EXCEPTION 'Creator maintenance must retry' USING ERRCODE='40001';
      END;
      -- Lock before inspecting completion. Otherwise a concurrent cleanup can
      -- cache zero while this update still exposes the formerly retained UUID.
      FOR candidate IN SELECT p.subject FROM public.account_financial_parties(NEW.user_id,NULL,NEW.tenant_id) p
        WHERE p.direct_reference ORDER BY hashtextextended('identity-retirement:'||p.subject,0),p.subject LOOP
        IF NOT pg_try_advisory_xact_lock_shared(hashtextextended('identity-retirement:'||candidate,0)) THEN
          RAISE EXCEPTION 'Creator maintenance must retry' USING ERRCODE='40001';
        END IF;
      END LOOP;
      IF EXISTS(SELECT 1 FROM public.account_financial_parties(NEW.user_id,NULL,NEW.tenant_id) p
          JOIN public.account_lifecycles a ON a.subject=p.subject WHERE p.direct_reference
          AND ((NEW.tenant_id IS NULL AND a.effects @> '{"company_creator_refs_unlinked": true}'::jsonb)
            OR EXISTS(SELECT 1 FROM public.account_lifecycle_scopes sc
              WHERE sc.subject=a.subject AND sc.tenant_id=NEW.tenant_id
                AND sc.effects @> '{"company_creator_refs_unlinked": true}'::jsonb))) THEN
        NEW.user_id:=NULL;
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_budget_creator_fence() FROM PUBLIC")
    op.execute("""CREATE TRIGGER aaa_budget_creator_fence BEFORE UPDATE ON public.crypto_agent_budgets
      FOR EACH ROW EXECUTE FUNCTION public.account_budget_creator_fence()""")


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("DROP TRIGGER aaa_budget_creator_fence ON public.crypto_agent_budgets")
    op.execute("DROP FUNCTION public.account_budget_creator_fence()")
    op.execute("DROP FUNCTION public.account_erase_personal_company_creators(text,timestamptz,uuid,integer)")
    op.execute("DROP FUNCTION public.account_personal_profile_ids(text,uuid)")
