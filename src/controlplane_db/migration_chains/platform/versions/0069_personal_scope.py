"""Coordinate personal association erasure and native authorization."""

from alembic import op

revision = "platform_0069_personal_scope"
down_revision = "platform_0068_inventory_gate"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""CREATE OR REPLACE FUNCTION public.account_bind_financial_source(
      p_subjects text[],p_tenant uuid,p_owner text,p_kind text,p_resource text)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE candidate text; inserted_count integer;
    BEGIN
      IF p_owner IS NULL OR p_owner NOT IN ('billing','payment','hypermesh')
        OR p_kind IS NULL OR p_kind !~ '^[a-z_]{1,48}$'
        OR p_resource IS NULL OR length(p_resource) NOT BETWEEN 1 AND 512
        OR coalesce(cardinality(p_subjects),0)>1000
        OR current_setting('transaction_isolation')<>'read committed' THEN
        RAISE EXCEPTION 'Native financial source binding required' USING ERRCODE='42501';
      END IF;
      FOR candidate IN SELECT value FROM (SELECT DISTINCT value FROM unnest(coalesce(p_subjects,ARRAY[]::text[])) value WHERE value IS NOT NULL) candidates
        ORDER BY hashtextextended('identity-retirement:'||value,0),value LOOP
        IF length(btrim(candidate))=0 OR length(candidate)>512 OR candidate LIKE 'apikey:%' THEN
          RAISE EXCEPTION 'Canonical financial identity required' USING ERRCODE='42501';
        END IF;
        IF NOT pg_try_advisory_xact_lock_shared(hashtextextended('identity-retirement:'||candidate,0)) THEN
          RAISE EXCEPTION 'Financial source binding must retry' USING ERRCODE='40001';
        END IF;
      END LOOP;
      FOR candidate IN SELECT DISTINCT value FROM unnest(coalesce(p_subjects,ARRAY[]::text[])) value
        WHERE value IS NOT NULL ORDER BY value LOOP
        BEGIN
          PERFORM 1 FROM public.account_lifecycles WHERE subject=candidate FOR UPDATE NOWAIT;
        EXCEPTION WHEN lock_not_available THEN
          RAISE EXCEPTION 'Financial lifecycle binding must retry' USING ERRCODE='40001';
        END;
        INSERT INTO public.account_financial_source_bindings(subject,tenant_id,owner,kind,resource)
          SELECT candidate,p_tenant,p_owner,p_kind,p_resource FROM public.account_lifecycles a
          WHERE a.subject=candidate AND a.financial_deleted_at IS NULL
            AND NOT (p_owner='hypermesh'
              AND p_kind IN ('host_organization_bindings','hypermesh_jobs','hypermesh_tunnels','hypermesh_tickets')
              AND ((p_tenant IS NULL AND a.effects @> '{"operational_sources_unlinked": true}'::jsonb)
                OR (p_tenant IS NOT NULL AND EXISTS(
                  SELECT 1 FROM public.account_lifecycle_scopes sc
                  WHERE sc.subject=candidate AND sc.tenant_id=p_tenant
                    AND sc.effects @> '{"operational_sources_unlinked": true}'::jsonb))))
          ON CONFLICT ON CONSTRAINT uq_account_financial_source DO NOTHING;
        GET DIAGNOSTICS inserted_count = ROW_COUNT;
        IF inserted_count>0 THEN
          UPDATE public.account_lifecycles SET financial_epoch=financial_epoch+1 WHERE subject=candidate;
        END IF;
      END LOOP;
    END $$""")
    op.execute("""CREATE FUNCTION public.account_require_personal_erasure(p_subject text,p_tenant uuid)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE original_closed_at timestamptz;
    BEGIN
      LOCK TABLE public.account_financial_fence_versions IN SHARE MODE;
      SELECT closed_at INTO original_closed_at FROM public.account_lifecycles WHERE subject=p_subject;
      PERFORM public.account_require_financial_inventory(p_subject,original_closed_at);
      PERFORM public.account_lock_financial_inventory(p_subject,original_closed_at,p_tenant);
      -- Only the trusted coordinator starts personal erasure after its recorded
      -- database-time boundary. No RPC age or caller GUC can authorize this.
      IF NOT EXISTS(SELECT 1 FROM public.account_lifecycles WHERE subject=p_subject
        AND state IN ('deleting','deleted')) THEN
        RAISE EXCEPTION 'Personal erasure has not been authorized' USING ERRCODE='42501';
      END IF;
    END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.account_require_personal_erasure(text,uuid) FROM PUBLIC"
    )
    op.execute("""CREATE FUNCTION public.account_unbind_hypermesh_personal_sources(p_subject text,p_tenant uuid)
    RETURNS integer LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE removed integer;
    BEGIN
      PERFORM public.account_require_personal_erasure(p_subject,p_tenant);
      -- Install the durable per-scope fence in the same transaction as unlinking.
      -- Later live-lease activity still invalidates financial proofs, but cannot
      -- recreate operational identity links after their erasure receipt.
      IF p_tenant IS NULL THEN
        UPDATE public.account_lifecycles SET effects=effects || '{"operational_sources_unlinked": true}'::jsonb
          WHERE subject=p_subject;
      ELSE
        UPDATE public.account_lifecycle_scopes SET effects=effects || '{"operational_sources_unlinked": true}'::jsonb
          WHERE subject=p_subject AND tenant_id=p_tenant;
      END IF;
      DELETE FROM public.account_financial_source_bindings
        WHERE subject=p_subject AND tenant_id IS NOT DISTINCT FROM p_tenant AND owner='hypermesh'
          AND kind IN ('host_organization_bindings','hypermesh_jobs','hypermesh_tunnels','hypermesh_tickets');
      GET DIAGNOSTICS removed=ROW_COUNT;
      IF removed>0 THEN
        PERFORM public.account_touch_financial_subjects(ARRAY[p_subject],ARRAY[]::text[]);
      END IF;
      RETURN removed;
    END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.account_unbind_hypermesh_personal_sources(text,uuid) FROM PUBLIC"
    )


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("""DO $$ BEGIN
      IF to_regprocedure('public.hypermesh_erase_personal_host_associations(text,timestamptz,uuid,integer)') IS NOT NULL THEN
        RAISE EXCEPTION 'Remove dependent host personal cleanup before its scope guard';
      END IF;
    END $$""")
    op.execute("""CREATE OR REPLACE FUNCTION public.account_bind_financial_source(
      p_subjects text[],p_tenant uuid,p_owner text,p_kind text,p_resource text)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE candidate text; inserted_count integer;
    BEGIN
      IF p_owner IS NULL OR p_owner NOT IN ('billing','payment','hypermesh')
        OR p_kind IS NULL OR p_kind !~ '^[a-z_]{1,48}$'
        OR p_resource IS NULL OR length(p_resource) NOT BETWEEN 1 AND 512
        OR coalesce(cardinality(p_subjects),0)>1000
        OR current_setting('transaction_isolation')<>'read committed' THEN
        RAISE EXCEPTION 'Native financial source binding required' USING ERRCODE='42501';
      END IF;
      FOR candidate IN SELECT value FROM (SELECT DISTINCT value FROM unnest(coalesce(p_subjects,ARRAY[]::text[])) value WHERE value IS NOT NULL) candidates
        ORDER BY hashtextextended('identity-retirement:'||value,0),value LOOP
        IF length(btrim(candidate))=0 OR length(candidate)>512 OR candidate LIKE 'apikey:%' THEN
          RAISE EXCEPTION 'Canonical financial identity required' USING ERRCODE='42501';
        END IF;
        IF NOT pg_try_advisory_xact_lock_shared(hashtextextended('identity-retirement:'||candidate,0)) THEN
          RAISE EXCEPTION 'Financial source binding must retry' USING ERRCODE='40001';
        END IF;
      END LOOP;
      FOR candidate IN SELECT DISTINCT value FROM unnest(coalesce(p_subjects,ARRAY[]::text[])) value
        WHERE value IS NOT NULL ORDER BY value LOOP
        BEGIN
          PERFORM 1 FROM public.account_lifecycles WHERE subject=candidate FOR UPDATE NOWAIT;
        EXCEPTION WHEN lock_not_available THEN
          RAISE EXCEPTION 'Financial lifecycle binding must retry' USING ERRCODE='40001';
        END;
        INSERT INTO public.account_financial_source_bindings(subject,tenant_id,owner,kind,resource)
          SELECT candidate,p_tenant,p_owner,p_kind,p_resource FROM public.account_lifecycles a
          WHERE a.subject=candidate AND a.financial_deleted_at IS NULL
          ON CONFLICT ON CONSTRAINT uq_account_financial_source DO NOTHING;
        GET DIAGNOSTICS inserted_count = ROW_COUNT;
        IF inserted_count>0 THEN
          UPDATE public.account_lifecycles SET financial_epoch=financial_epoch+1 WHERE subject=candidate;
        END IF;
      END LOOP;
    END $$""")
    op.execute(
        "DROP FUNCTION public.account_unbind_hypermesh_personal_sources(text,uuid)"
    )
    op.execute("DROP FUNCTION public.account_require_personal_erasure(text,uuid)")
