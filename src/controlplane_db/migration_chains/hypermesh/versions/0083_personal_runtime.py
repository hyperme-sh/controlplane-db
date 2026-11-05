"""Erase terminal renter credentials while keeping running work and host peers."""

from alembic import op

revision = "hypermesh_0083_personal_runtime"
down_revision = "hypermesh_0082_personal_hosts"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""DO $$ BEGIN
      IF to_regprocedure('public.account_personal_renter_leases(text,uuid)') IS NULL THEN
        RAISE EXCEPTION 'Original personal renter projection is not installed';
      END IF;
    END $$""")
    op.execute("""CREATE FUNCTION public.hypermesh_erase_personal_runtime(
      p_subject text,p_closed_at timestamptz,p_tenant uuid,p_limit integer DEFAULT 100)
    RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE leases uuid[]; item record; processed integer:=0; remaining bigint;
    BEGIN
      PERFORM public.account_lock_financial_inventory(p_subject,p_closed_at,p_tenant);
      leases:=public.account_personal_renter_leases(p_subject,p_tenant);
      PERFORM public.account_unbind_hypermesh_personal_sources(p_subject,p_tenant);
      IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 1000 THEN
        RAISE EXCEPTION 'Bounded runtime cleanup batch required' USING ERRCODE='42501';
      END IF;
      -- Failed starts can be cancelled by the server without a host timestamp.
      -- Their terminal status is authoritative; do not invent completion times.
      -- Unpaid offers grant no running authority and need no lifecycle mutation.
      -- Lock each non-running contract with the credential before changing either
      -- association. A concurrent lifecycle change must retry the whole effect.
      FOR item IN SELECT j.id FROM public.hypermesh_jobs j JOIN public.hypermesh_leases l
        ON l.id=j.lease_id AND l.tenant_id=j.tenant_id
        WHERE j.tenant_id=p_tenant AND j.lease_id=ANY(leases)
          AND (j.ticket IS NOT NULL OR j.dispatch_skip_reason IS NOT NULL)
          AND l.status IN ('offered','ended','failed','refunded')
          AND j.status IN ('passed','failed')
        ORDER BY j.id LIMIT p_limit FOR UPDATE OF j,l NOWAIT LOOP
        UPDATE public.hypermesh_jobs SET ticket=NULL,dispatch_skip_reason=NULL WHERE id=item.id;
        processed:=processed+1;
      END LOOP;
      FOR item IN SELECT t.lease_id FROM public.hypermesh_tickets t JOIN public.hypermesh_leases l
        ON l.id=t.lease_id AND l.tenant_id=t.tenant_id
        WHERE t.tenant_id=p_tenant AND t.lease_id=ANY(leases)
          AND t.status='revoked' AND t.exp<=transaction_timestamp()
          AND l.status IN ('offered','ended','failed','refunded')
        ORDER BY t.lease_id LIMIT p_limit FOR UPDATE OF t,l NOWAIT LOOP
        DELETE FROM public.hypermesh_tickets WHERE tenant_id=p_tenant AND lease_id=item.lease_id;
        processed:=processed+1;
      END LOOP;
      -- Match ordinary lease completion: detach the expired renter association;
      -- keep the host's standing peer, keys, address, status and acknowledgement.
      FOR item IN SELECT t.id FROM public.hypermesh_tunnels t JOIN public.hypermesh_leases l
        ON l.id=t.lease_id AND l.tenant_id=t.tenant_id
        WHERE t.tenant_id=p_tenant AND t.lease_id=ANY(leases)
          AND l.status IN ('offered','ended','failed','refunded')
        ORDER BY t.id LIMIT p_limit FOR UPDATE OF t,l NOWAIT LOOP
        UPDATE public.hypermesh_tunnels SET lease_id=NULL,expires_at=NULL WHERE id=item.id;
        processed:=processed+1;
      END LOOP;
      SELECT (SELECT count(*) FROM public.hypermesh_jobs WHERE tenant_id=p_tenant
        AND lease_id=ANY(leases) AND (ticket IS NOT NULL OR dispatch_skip_reason IS NOT NULL
          OR status NOT IN ('passed','failed')))
        +(SELECT count(*) FROM public.hypermesh_tickets WHERE tenant_id=p_tenant AND lease_id=ANY(leases))
        +(SELECT count(*) FROM public.hypermesh_tunnels WHERE tenant_id=p_tenant AND lease_id=ANY(leases))
        +(SELECT count(*) FROM public.hypermesh_leases WHERE tenant_id=p_tenant AND id=ANY(leases)
          AND status NOT IN ('offered','ended','failed','refunded'))
        INTO remaining;
      IF remaining=0 THEN
        PERFORM public.account_mark_personal_runtime_erased(p_subject,p_tenant);
      END IF;
      RETURN jsonb_build_object('complete',remaining=0,'processed',processed,'remaining',remaining);
    EXCEPTION WHEN lock_not_available THEN
      RAISE EXCEPTION 'Personal runtime cleanup must retry' USING ERRCODE='40001';
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.hypermesh_erase_personal_runtime(text,timestamptz,uuid,integer) FROM PUBLIC")

    op.execute("""CREATE FUNCTION public.hypermesh_personal_runtime_admission()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$ BEGIN
      IF TG_TABLE_NAME='hypermesh_jobs' THEN
        IF NEW.lease_id IS NULL OR NEW.ticket IS NULL THEN RETURN NEW; END IF;
        IF TG_OP='UPDATE' AND NEW.lease_id IS NOT DISTINCT FROM OLD.lease_id
          AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id
          AND NEW.ticket IS NOT DISTINCT FROM OLD.ticket THEN RETURN NEW; END IF;
      ELSE
        IF NEW.lease_id IS NULL THEN RETURN NEW; END IF;
        IF TG_OP='UPDATE' AND NEW.lease_id IS NOT DISTINCT FROM OLD.lease_id
          AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id THEN RETURN NEW; END IF;
      END IF;
      PERFORM public.account_require_runtime_lease_reference(NEW.tenant_id,NEW.lease_id);
      RETURN NEW;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.hypermesh_personal_runtime_admission() FROM PUBLIC")
    op.execute("""CREATE TRIGGER account_runtime_admission BEFORE INSERT OR UPDATE ON public.hypermesh_jobs
      FOR EACH ROW EXECUTE FUNCTION public.hypermesh_personal_runtime_admission()""")
    op.execute("""CREATE TRIGGER account_runtime_admission BEFORE INSERT OR UPDATE ON public.hypermesh_tunnels
      FOR EACH ROW EXECUTE FUNCTION public.hypermesh_personal_runtime_admission()""")


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("DROP TRIGGER account_runtime_admission ON public.hypermesh_jobs")
    op.execute("DROP TRIGGER account_runtime_admission ON public.hypermesh_tunnels")
    op.execute("DROP FUNCTION public.hypermesh_personal_runtime_admission()")
    op.execute("DROP FUNCTION public.hypermesh_erase_personal_runtime(text,timestamptz,uuid,integer)")
