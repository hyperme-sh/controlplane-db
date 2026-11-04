"""Project original personal renter contracts for runtime credential cleanup."""

from alembic import op

revision = "platform_0070_renter_scope"
down_revision = "platform_0069_personal_scope"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""CREATE FUNCTION public.account_personal_renter_leases(p_subject text,p_tenant uuid)
    RETURNS uuid[] LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE inventory jsonb; result uuid[];
    BEGIN
      PERFORM public.account_require_personal_erasure(p_subject,p_tenant);
      IF p_tenant IS NULL THEN RETURN ARRAY[]::uuid[]; END IF;
      SELECT effects->'hypermesh' INTO inventory FROM public.account_lifecycle_scopes
        WHERE subject=p_subject AND tenant_id=p_tenant;
      IF inventory IS NULL OR NOT (inventory @> '{"tickets_revoked": true,"new_selling_disabled": true}'::jsonb)
        OR jsonb_typeof(inventory->'lease_ids') IS DISTINCT FROM 'array' THEN
        RAISE EXCEPTION 'Original renter contract inventory required' USING ERRCODE='42501';
      END IF;
      IF jsonb_array_length(inventory->'lease_ids')>100000 OR EXISTS(
        SELECT 1 FROM jsonb_array_elements_text(inventory->'lease_ids') value
        WHERE value IS NULL OR value !~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$') THEN
        RAISE EXCEPTION 'Canonical renter contract inventory required' USING ERRCODE='42501';
      END IF;
      SELECT coalesce(array_agg(DISTINCT value::uuid),ARRAY[]::uuid[]) INTO result
        FROM jsonb_array_elements_text(inventory->'lease_ids') value;
      RETURN result;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_personal_renter_leases(text,uuid) FROM PUBLIC")

    op.execute("""CREATE FUNCTION public.account_mark_personal_runtime_erased(p_subject text,p_tenant uuid)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$ BEGIN
      PERFORM public.account_require_personal_erasure(p_subject,p_tenant);
      IF p_tenant IS NULL THEN
        UPDATE public.account_lifecycles SET effects=effects || '{"runtime_credentials_unlinked": true}'::jsonb
          WHERE subject=p_subject;
      ELSE
        UPDATE public.account_lifecycle_scopes SET effects=effects || '{"runtime_credentials_unlinked": true}'::jsonb
          WHERE subject=p_subject AND tenant_id=p_tenant;
      END IF;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_mark_personal_runtime_erased(text,uuid) FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.account_require_runtime_lease_reference(p_tenant uuid,p_lease uuid)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE candidate text;
    BEGIN
      IF current_setting('transaction_isolation')<>'read committed' THEN
        RAISE EXCEPTION 'Runtime reference requires READ COMMITTED isolation' USING ERRCODE='42501';
      END IF;
      -- Outer source writes can already hold their own row. All waits here
      -- are nonblocking, preserving the native retirement/source lock order.
      BEGIN
        LOCK TABLE public.account_financial_fence_versions IN SHARE MODE NOWAIT;
      EXCEPTION WHEN lock_not_available THEN
        RAISE EXCEPTION 'Runtime reference must retry' USING ERRCODE='40001';
      END;
      FOR candidate IN SELECT subject FROM public.account_lifecycle_scopes
        WHERE tenant_id=p_tenant AND effects->'hypermesh'->'lease_ids' @> jsonb_build_array(p_lease::text)
        ORDER BY hashtextextended('identity-retirement:'||subject,0),subject LOOP
        IF NOT pg_try_advisory_xact_lock_shared(hashtextextended('identity-retirement:'||candidate,0)) THEN
          RAISE EXCEPTION 'Runtime reference must retry' USING ERRCODE='40001';
        END IF;
        BEGIN
          PERFORM 1 FROM public.account_lifecycles WHERE subject=candidate FOR UPDATE NOWAIT;
        EXCEPTION WHEN lock_not_available THEN
          RAISE EXCEPTION 'Runtime lifecycle reference must retry' USING ERRCODE='40001';
        END;
      END LOOP;
      IF EXISTS(SELECT 1 FROM public.account_lifecycle_scopes
        WHERE tenant_id=p_tenant AND effects->'hypermesh'->'lease_ids' @> jsonb_build_array(p_lease::text)
          AND effects @> '{"runtime_credentials_unlinked": true}'::jsonb) THEN
        RAISE EXCEPTION 'Erased renter runtime credentials cannot be recaptured' USING ERRCODE='42501';
      END IF;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_require_runtime_lease_reference(uuid,uuid) FROM PUBLIC")


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("""DO $$ BEGIN
      IF to_regprocedure('public.hypermesh_erase_personal_runtime(text,timestamptz,uuid,integer)') IS NOT NULL THEN
        RAISE EXCEPTION 'Remove dependent runtime cleanup before its renter scope';
      END IF;
    END $$""")
    op.execute("DROP FUNCTION public.account_require_runtime_lease_reference(uuid,uuid)")
    op.execute("DROP FUNCTION public.account_mark_personal_runtime_erased(text,uuid)")
    op.execute("DROP FUNCTION public.account_personal_renter_leases(text,uuid)")
