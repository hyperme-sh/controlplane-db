"""Erase copied reviewer identity without changing a company intake decision."""

from alembic import op

revision = "hypermesh_0085_reviewers"
down_revision = "hypermesh_0084_model_wait"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""CREATE FUNCTION public.hypermesh_erase_personal_device_reviewers(
      p_subject text,p_closed_at timestamptz,p_tenant uuid,p_limit integer DEFAULT 100)
    RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE item record; processed integer:=0; remaining bigint;
    BEGIN
      PERFORM public.account_lock_financial_inventory(p_subject,p_closed_at,p_tenant);
      PERFORM public.account_require_personal_erasure(p_subject,p_tenant);
      IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 1000 THEN
        RAISE EXCEPTION 'Bounded reviewer cleanup required' USING ERRCODE='42501';
      END IF;
      FOR item IN SELECT id FROM public.hypermesh_devices
        WHERE tenant_id IS NOT DISTINCT FROM p_tenant
          AND jsonb_typeof(path_a)='object' AND path_a->>'reviewed_by'=p_subject
        ORDER BY id LIMIT p_limit FOR UPDATE NOWAIT LOOP
        UPDATE public.hypermesh_devices SET path_a=path_a-'reviewed_by' WHERE id=item.id;
        processed:=processed+1;
      END LOOP;
      SELECT count(*) INTO remaining FROM public.hypermesh_devices
        WHERE tenant_id IS NOT DISTINCT FROM p_tenant
          AND jsonb_typeof(path_a)='object' AND path_a->>'reviewed_by'=p_subject;
      RETURN jsonb_build_object('complete',remaining=0,'processed',processed,'remaining',remaining);
    EXCEPTION WHEN lock_not_available THEN
      RAISE EXCEPTION 'Reviewer cleanup must retry' USING ERRCODE='40001';
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.hypermesh_erase_personal_device_reviewers(text,timestamptz,uuid,integer) FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.hypermesh_device_reviewer_admission()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE reviewer text:=NEW.path_a->>'reviewed_by';
    BEGIN
      IF reviewer IS NULL THEN RETURN NEW; END IF;
      IF TG_OP='UPDATE' AND NEW.path_a IS NOT DISTINCT FROM OLD.path_a THEN
        RETURN NEW;
      END IF;
      IF jsonb_typeof(NEW.path_a->'reviewed_by') IS DISTINCT FROM 'string'
        OR length(btrim(reviewer))=0 OR length(reviewer)>512 OR reviewer LIKE 'apikey:%' THEN
        RAISE EXCEPTION 'Canonical reviewer identity required' USING ERRCODE='42501';
      END IF;
      IF NOT pg_try_advisory_xact_lock(hashtextextended('identity-retirement:'||reviewer,0)) THEN
        RAISE EXCEPTION 'Reviewer admission must retry' USING ERRCODE='40001';
      END IF;
      PERFORM public.account_require_open_subjects(ARRAY[reviewer]);
      RETURN NEW;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.hypermesh_device_reviewer_admission() FROM PUBLIC")
    op.execute("""CREATE TRIGGER account_reviewer_admission BEFORE INSERT OR UPDATE ON public.hypermesh_devices
      FOR EACH ROW EXECUTE FUNCTION public.hypermesh_device_reviewer_admission()""")


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("DROP TRIGGER account_reviewer_admission ON public.hypermesh_devices")
    op.execute("DROP FUNCTION public.hypermesh_device_reviewer_admission()")
    op.execute("DROP FUNCTION public.hypermesh_erase_personal_device_reviewers(text,timestamptz,uuid,integer)")
