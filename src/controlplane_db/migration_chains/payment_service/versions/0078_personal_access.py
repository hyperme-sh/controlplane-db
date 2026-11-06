"""Scrub access-session actors while preserving company money fences."""

from alembic import op

revision = "payment_service_0078_privacy"
down_revision = "payment_service_0077_fin_inv"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""DO $$ BEGIN
      IF to_regprocedure('public.account_lock_personal_access_actor(text,uuid)') IS NULL
        OR to_regprocedure('public.account_unbind_personal_access_actor(text,uuid,uuid)') IS NULL THEN
        RAISE EXCEPTION 'Native access actor authorization is not installed';
      END IF;
    END $$""")
    op.execute("""CREATE FUNCTION public.payment_access_actor_redaction()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE replacement text:='closed-access:'||OLD.id::text;
    BEGIN
      IF NEW.owner_sub IS DISTINCT FROM replacement
        OR NEW.member_id IS DISTINCT FROM replacement
        OR NEW.issuer_session IS DISTINCT FROM replacement
        OR (to_jsonb(NEW)-ARRAY['owner_sub','member_id','issuer_session']) IS DISTINCT FROM
           (to_jsonb(OLD)-ARRAY['owner_sub','member_id','issuer_session']) THEN
        RAISE EXCEPTION 'Access journal is immutable' USING ERRCODE='23514';
      END IF;
      PERFORM public.account_lock_personal_access_actor(OLD.owner_sub,OLD.tenant_id);
      RETURN NEW;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.payment_access_actor_redaction() FROM PUBLIC")
    op.execute("DROP TRIGGER connect_access_grants_update ON public.connect_access_grants")
    op.execute("""CREATE TRIGGER connect_access_grants_update BEFORE UPDATE ON public.connect_access_grants
      FOR EACH ROW EXECUTE FUNCTION public.payment_access_actor_redaction()""")
    op.execute("""CREATE FUNCTION public.payment_access_actor_unlink()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$ BEGIN
      PERFORM public.account_unbind_personal_access_actor(OLD.owner_sub,OLD.tenant_id,OLD.id);
      RETURN NEW;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.payment_access_actor_unlink() FROM PUBLIC")
    op.execute("""CREATE TRIGGER zz_access_actor_unlink AFTER UPDATE ON public.connect_access_grants
      FOR EACH ROW EXECUTE FUNCTION public.payment_access_actor_unlink()""")
    op.execute("""CREATE FUNCTION public.payment_access_owner_admission()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE actor text:=NEW.lifecycle->'owner'->>'subject';
    BEGIN
      IF actor IS NULL THEN RETURN NEW; END IF;
      IF TG_OP='UPDATE' AND NEW.lifecycle->'owner' IS NOT DISTINCT FROM OLD.lifecycle->'owner'
        AND NOT (NEW.enabled AND NOT OLD.enabled) THEN RETURN NEW; END IF;
      IF NOT pg_try_advisory_xact_lock(hashtextextended('identity-retirement:'||actor,0)) THEN
        RAISE EXCEPTION 'Access owner admission must retry' USING ERRCODE='40001';
      END IF;
      PERFORM public.account_require_open_subjects(ARRAY[actor]);
      RETURN NEW;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.payment_access_owner_admission() FROM PUBLIC")
    op.execute("""CREATE TRIGGER account_access_owner_admission BEFORE INSERT OR UPDATE ON public.connect_access_states
      FOR EACH ROW EXECUTE FUNCTION public.payment_access_owner_admission()""")
    op.execute("""CREATE FUNCTION public.payment_erase_personal_access(
      p_subject text,p_closed_at timestamptz,p_tenant uuid,p_limit integer DEFAULT 100)
    RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE item record; processed integer:=0; remaining bigint;
    BEGIN
      PERFORM public.account_lock_financial_inventory(p_subject,p_closed_at,p_tenant);
      PERFORM public.account_require_personal_erasure(p_subject,p_tenant);
      IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 1000 THEN
        RAISE EXCEPTION 'Bounded access cleanup required' USING ERRCODE='42501';
      END IF;
      FOR item IN SELECT host_org_id FROM public.connect_access_states
        WHERE tenant_id=p_tenant AND lifecycle->'owner'->>'subject'=p_subject
        ORDER BY host_org_id LIMIT p_limit FOR UPDATE NOWAIT LOOP
        UPDATE public.connect_access_states SET enabled=false,epoch=epoch+1,lifecycle=lifecycle-'owner'
          WHERE tenant_id=p_tenant AND host_org_id=item.host_org_id;
        processed:=processed+1;
      END LOOP;
      FOR item IN SELECT id FROM public.connect_access_grants
        WHERE tenant_id=p_tenant AND owner_sub=p_subject ORDER BY id LIMIT p_limit FOR UPDATE NOWAIT LOOP
        UPDATE public.connect_access_grants SET owner_sub='closed-access:'||id::text,
          member_id='closed-access:'||id::text,issuer_session='closed-access:'||id::text WHERE id=item.id;
        -- The AFTER redaction trigger unlinks the old actor after the native
        -- source epoch trigger. Direct authorized redaction has the same fence.
        -- Grant/results and native expiry remain unchanged for money safety.
        processed:=processed+1;
      END LOOP;
      SELECT (SELECT count(*) FROM public.connect_access_states
          WHERE tenant_id=p_tenant AND lifecycle->'owner'->>'subject'=p_subject)
        +(SELECT count(*) FROM public.connect_access_grants WHERE tenant_id=p_tenant AND owner_sub=p_subject)
        INTO remaining;
      RETURN jsonb_build_object('complete',remaining=0,'processed',processed,'remaining',remaining);
    EXCEPTION WHEN lock_not_available THEN
      RAISE EXCEPTION 'Access cleanup must retry' USING ERRCODE='40001';
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.payment_erase_personal_access(text,timestamptz,uuid,integer) FROM PUBLIC")


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("DROP TRIGGER account_access_owner_admission ON public.connect_access_states")
    op.execute("DROP FUNCTION public.payment_access_owner_admission()")
    op.execute("DROP TRIGGER zz_access_actor_unlink ON public.connect_access_grants")
    op.execute("DROP FUNCTION public.payment_access_actor_unlink()")
    op.execute("DROP FUNCTION public.payment_erase_personal_access(text,timestamptz,uuid,integer)")
    op.execute("DROP TRIGGER connect_access_grants_update ON public.connect_access_grants")
    op.execute("""CREATE TRIGGER connect_access_grants_update BEFORE UPDATE ON public.connect_access_grants
      FOR EACH ROW EXECUTE FUNCTION public.connect_recipient_immutable()""")
    op.execute("DROP FUNCTION public.payment_access_actor_redaction()")
