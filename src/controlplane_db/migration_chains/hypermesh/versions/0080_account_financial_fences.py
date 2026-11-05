"""Version Hypermesh financial sources without retiring running workloads."""

import sqlalchemy as sa
from alembic import op

revision = "hypermesh_0080_financial"
down_revision = "hypermesh_0079_model_erasure"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_fence_changes()")
    op.execute("SET LOCAL row_security=off")
    op.add_column(
        "hypermesh_leases",
        sa.Column("financial_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hypermesh_leases",
        sa.Column("financial_retain_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_hypermesh_leases_financial_clock",
        "hypermesh_leases",
        "(financial_activity_at IS NULL AND financial_retain_until IS NULL) OR (financial_activity_at IS NOT NULL AND financial_retain_until IS NOT NULL AND financial_retain_until > financial_activity_at)",
    )
    op.create_index(
        "ix_hypermesh_leases_financial_due",
        "hypermesh_leases",
        ["financial_retain_until"],
    )
    op.add_column(
        "hypermesh_payouts",
        sa.Column("financial_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hypermesh_payouts",
        sa.Column("financial_retain_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_hypermesh_payouts_financial_clock",
        "hypermesh_payouts",
        "(financial_activity_at IS NULL AND financial_retain_until IS NULL) OR (financial_activity_at IS NOT NULL AND financial_retain_until IS NOT NULL AND financial_retain_until > financial_activity_at)",
    )
    op.create_index(
        "ix_hypermesh_payouts_financial_due",
        "hypermesh_payouts",
        ["financial_retain_until"],
    )
    op.add_column(
        "hypermesh_orders",
        sa.Column("financial_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hypermesh_orders",
        sa.Column("financial_retain_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_hypermesh_orders_financial_clock",
        "hypermesh_orders",
        "(financial_activity_at IS NULL AND financial_retain_until IS NULL) OR (financial_activity_at IS NOT NULL AND financial_retain_until IS NOT NULL AND financial_retain_until > financial_activity_at)",
    )
    op.create_index(
        "ix_hypermesh_orders_financial_due",
        "hypermesh_orders",
        ["financial_retain_until"],
    )
    op.add_column(
        "hypermesh_fills",
        sa.Column("financial_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "hypermesh_fills",
        sa.Column("financial_retain_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_hypermesh_fills_financial_clock",
        "hypermesh_fills",
        "(financial_activity_at IS NULL AND financial_retain_until IS NULL) OR (financial_activity_at IS NOT NULL AND financial_retain_until IS NOT NULL AND financial_retain_until > financial_activity_at)",
    )
    op.create_index(
        "ix_hypermesh_fills_financial_due",
        "hypermesh_fills",
        ["financial_retain_until"],
    )
    # Preserve native lifecycle/payment anchors. Neither rollout nor closure
    # starts a fresh retention period. Historical payout/order/fill rows have
    # no own last-change timestamp. A parent lease's date cannot prove when a
    # payout was recorded; leave these clocks unknown for reconciliation.
    op.execute("""UPDATE public.hypermesh_leases l SET
      financial_activity_at=greatest(l.created_at,l.activated_at,l.ended_at,l.failed_at,
        (public.account_billing_financial_source(l.billing_record_id,l.tenant_id)->>'financial_activity_at')::timestamptz),
      financial_retain_until=((greatest(l.created_at,l.activated_at,l.ended_at,l.failed_at,
        (public.account_billing_financial_source(l.billing_record_id,l.tenant_id)->>'financial_activity_at')::timestamptz)
        AT TIME ZONE 'UTC')+interval '7 years') AT TIME ZONE 'UTC'""")
    op.execute("""CREATE FUNCTION public.hypermesh_financial_clock()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
    DECLARE current_facts jsonb; previous_facts jsonb; current_pin jsonb; previous_pin jsonb;
    BEGIN
      IF TG_OP='INSERT' THEN
        IF NEW.financial_activity_at IS NOT NULL OR NEW.financial_retain_until IS NOT NULL THEN
          RAISE EXCEPTION 'Native financial clocks are server recorded' USING ERRCODE='42501';
        END IF;
        NEW.financial_activity_at:=clock_timestamp();
      ELSE
        IF NEW.financial_activity_at IS DISTINCT FROM OLD.financial_activity_at
          OR NEW.financial_retain_until IS DISTINCT FROM OLD.financial_retain_until THEN
          RAISE EXCEPTION 'Native financial clocks cannot be supplied' USING ERRCODE='42501';
        END IF;
        current_facts:=to_jsonb(NEW)-ARRAY['financial_activity_at','financial_retain_until'];
        previous_facts:=to_jsonb(OLD)-ARRAY['financial_activity_at','financial_retain_until'];
        IF TG_TABLE_NAME='hypermesh_leases' THEN
          current_pin:=to_jsonb(NEW)->'private_model'; previous_pin:=to_jsonb(OLD)->'private_model';
          IF previous_pin ? 'target' AND current_pin=previous_pin-'target'
            AND to_jsonb(OLD)->>'status' IN ('offered','ended','failed','refunded') THEN
            -- The existing immutable-pin trigger independently requires exact
            -- physical cleanup/closure evidence for this one-way target removal.
            -- Erasing that personal target must not extend financial retention.
            current_facts:=current_facts-'private_model'; previous_facts:=previous_facts-'private_model';
          END IF;
        END IF;
        IF current_facts IS DISTINCT FROM previous_facts THEN
          NEW.financial_activity_at:=greatest(OLD.financial_activity_at,clock_timestamp());
        END IF;
      END IF;
      NEW.financial_retain_until:=((NEW.financial_activity_at AT TIME ZONE 'UTC')+interval '7 years') AT TIME ZONE 'UTC';
      RETURN NEW;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.hypermesh_financial_clock() FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.hypermesh_financial_parties(p_table text,p_source jsonb)
    RETURNS TABLE(subject text,direct_reference boolean) LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE source_tenant uuid; source_id text; lease_record jsonb; native_host uuid;
      owner_sub text; billing_record jsonb; native_renter uuid;
    BEGIN
      IF p_table NOT IN ('hypermesh_leases','hypermesh_payouts','hypermesh_orders','hypermesh_fills',
        'hypermesh_jobs','hypermesh_tunnels','hypermesh_tickets','host_organization_bindings') THEN
        RAISE EXCEPTION 'Native Hypermesh financial source required' USING ERRCODE='42501';
      END IF;
      source_tenant:=(p_source->>'tenant_id')::uuid;
      source_id:=coalesce(p_source->>'id',p_source->>'order_id',p_source->>'lease_id',p_source->>'organization_id');
      RETURN QUERY SELECT p.subject,false FROM public.account_financial_parties(NULL,NULL,source_tenant,
        'hypermesh',p_table,source_id) p;
      IF p_table='host_organization_bindings' THEN
        RETURN QUERY SELECT p.subject,p.direct_reference FROM public.account_financial_parties(NULL,
          p_source->>'keycloak_sub',source_tenant) p;
        RETURN;
      END IF;
      IF p_table='hypermesh_leases' THEN lease_record:=p_source;
      ELSIF (p_source->>'lease_id') IS NOT NULL THEN
        SELECT to_jsonb(l) INTO lease_record FROM public.hypermesh_leases l
          WHERE l.id=(p_source->>'lease_id')::uuid AND l.tenant_id=source_tenant;
      END IF;
      IF lease_record IS NOT NULL THEN
        native_renter:=(lease_record->>'renter_user_id')::uuid;
        -- Historical renter slots contain either a directory UUID or the
        -- native UUID-shaped issuer subject. Resolve both for invalidation;
        -- the owner must separately prove unambiguous erasure ownership.
        RETURN QUERY SELECT p.subject,p.direct_reference FROM public.account_financial_parties(
          native_renter,native_renter::text,source_tenant,'hypermesh','hypermesh_leases',lease_record->>'id') p;
        IF lease_record->>'billing_record_id' IS NOT NULL THEN
          billing_record:=public.account_billing_financial_source((lease_record->>'billing_record_id')::uuid,source_tenant);
          RETURN QUERY SELECT p.subject,p.direct_reference FROM public.account_financial_parties(
            (billing_record->>'user_id')::uuid,billing_record->'metadata'->>'actor_sub',source_tenant,
            'billing','payment',lease_record->>'billing_record_id') p;
        END IF;
        native_host:=(lease_record->>'host_org_id')::uuid;
        IF native_host IS NULL AND lease_record->>'device_id' IS NOT NULL THEN
          SELECT d.host_org_id INTO native_host FROM public.hypermesh_devices d
            WHERE d.id=(lease_record->>'device_id')::uuid AND d.tenant_id=source_tenant;
        END IF;
      END IF;
      native_host:=coalesce((p_source->>'host_org_id')::uuid,native_host);
      -- Standing host peers and device jobs can have no lease. Resolve their
      -- own device independently, retaining the indirect company association.
      IF native_host IS NULL AND p_source->>'device_id' IS NOT NULL THEN
        SELECT d.host_org_id INTO native_host FROM public.hypermesh_devices d
          WHERE d.id=(p_source->>'device_id')::uuid AND d.tenant_id=source_tenant;
      END IF;
      IF native_host IS NOT NULL THEN
        SELECT b.keycloak_sub INTO owner_sub FROM public.host_organization_bindings b
          WHERE b.tenant_id=source_tenant AND b.organization_id=native_host;
        -- The row stores an organization reference. Its administrator/creator
        -- association is indirect and grants no legal ownership or recapture.
        RETURN QUERY SELECT p.subject,false FROM public.account_financial_parties(NULL,owner_sub,source_tenant,
          'hypermesh','host_organization_bindings',native_host::text) p;
      END IF;
      IF p_source->>'org_id' IS NOT NULL THEN
        -- Pricing org IDs are opaque. A literal canonical-subject alias
        -- fences recapture, but still grants no legal ownership or deletion
        -- authority over a company order or another payer.
        RETURN QUERY SELECT p.subject,p.direct_reference FROM public.account_financial_parties(NULL,p_source->>'org_id',source_tenant) p;
        SELECT b.keycloak_sub,b.organization_id INTO owner_sub,native_host
          FROM public.host_organization_bindings b
          WHERE b.tenant_id=source_tenant AND b.organization_id::text=p_source->>'org_id';
        IF FOUND THEN
          RETURN QUERY SELECT p.subject,false FROM public.account_financial_parties(NULL,owner_sub,source_tenant,
            'hypermesh','host_organization_bindings',native_host::text) p;
        END IF;
      END IF;
    END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.hypermesh_financial_parties(text,jsonb) FROM PUBLIC"
    )
    op.execute("""CREATE FUNCTION public.hypermesh_account_financial_epoch()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE source_record jsonb; canonical text[]:=ARRAY[]::text[]; captures text[]:=ARRAY[]::text[];
      source_subjects text[]; source_captures text[];
    BEGIN
      IF TG_OP='UPDATE' AND
        (to_jsonb(NEW)-ARRAY['financial_activity_at','financial_retain_until']) IS NOT DISTINCT FROM
        (to_jsonb(OLD)-ARRAY['financial_activity_at','financial_retain_until']) THEN RETURN NEW; END IF;
      FOR source_record IN SELECT item FROM unnest(CASE WHEN TG_OP='INSERT' THEN ARRAY[to_jsonb(NEW)]
        WHEN TG_OP='DELETE' THEN ARRAY[to_jsonb(OLD)] ELSE ARRAY[to_jsonb(OLD),to_jsonb(NEW)] END) item LOOP
        SELECT array_agg(p.subject),array_agg(p.subject) FILTER(WHERE p.direct_reference)
          INTO source_subjects,source_captures FROM public.hypermesh_financial_parties(TG_TABLE_NAME,source_record) p;
        canonical:=canonical||coalesce(source_subjects,ARRAY[]::text[]);
        IF TG_OP<>'DELETE' AND source_record=to_jsonb(NEW) THEN captures:=captures||coalesce(source_captures,ARRAY[]::text[]); END IF;
      END LOOP;
      SELECT array_agg(DISTINCT item) INTO canonical FROM unnest(canonical) item WHERE item IS NOT NULL;
      SELECT coalesce(array_agg(DISTINCT item),ARRAY[]::text[]) INTO captures FROM unnest(captures) item WHERE item IS NOT NULL;
      PERFORM public.account_touch_financial_subjects(canonical,captures);
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      PERFORM public.account_bind_financial_source(canonical,(to_jsonb(NEW)->>'tenant_id')::uuid,'hypermesh',TG_TABLE_NAME,
        coalesce(to_jsonb(NEW)->>'id',to_jsonb(NEW)->>'order_id',to_jsonb(NEW)->>'lease_id',to_jsonb(NEW)->>'organization_id'));
      RETURN NEW;
    END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.hypermesh_account_financial_epoch() FROM PUBLIC"
    )
    op.execute(
        "CREATE TRIGGER account_financial_clock BEFORE INSERT OR UPDATE ON public.hypermesh_leases FOR EACH ROW EXECUTE FUNCTION public.hypermesh_financial_clock()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_clock BEFORE INSERT OR UPDATE ON public.hypermesh_payouts FOR EACH ROW EXECUTE FUNCTION public.hypermesh_financial_clock()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_clock BEFORE INSERT OR UPDATE ON public.hypermesh_orders FOR EACH ROW EXECUTE FUNCTION public.hypermesh_financial_clock()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_clock BEFORE INSERT OR UPDATE ON public.hypermesh_fills FOR EACH ROW EXECUTE FUNCTION public.hypermesh_financial_clock()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.hypermesh_leases FOR EACH ROW EXECUTE FUNCTION public.hypermesh_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.hypermesh_leases FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.hypermesh_payouts FOR EACH ROW EXECUTE FUNCTION public.hypermesh_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.hypermesh_payouts FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.hypermesh_orders FOR EACH ROW EXECUTE FUNCTION public.hypermesh_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.hypermesh_orders FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.hypermesh_fills FOR EACH ROW EXECUTE FUNCTION public.hypermesh_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.hypermesh_fills FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.hypermesh_jobs FOR EACH ROW EXECUTE FUNCTION public.hypermesh_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.hypermesh_jobs FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.hypermesh_tunnels FOR EACH ROW EXECUTE FUNCTION public.hypermesh_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.hypermesh_tunnels FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.hypermesh_tickets FOR EACH ROW EXECUTE FUNCTION public.hypermesh_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.hypermesh_tickets FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.host_organization_bindings FOR EACH ROW EXECUTE FUNCTION public.hypermesh_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.host_organization_bindings FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute("SELECT public.account_register_financial_fence('hypermesh',1)")


def downgrade():
    op.execute("SELECT public.account_lock_financial_fence_changes()")
    op.execute("SELECT public.account_unregister_financial_fence('hypermesh')")
    op.execute("SET LOCAL row_security=off")
    op.execute("LOCK TABLE public.hypermesh_leases IN ACCESS EXCLUSIVE MODE")
    op.execute("LOCK TABLE public.hypermesh_payouts IN ACCESS EXCLUSIVE MODE")
    op.execute("LOCK TABLE public.hypermesh_orders IN ACCESS EXCLUSIVE MODE")
    op.execute("LOCK TABLE public.hypermesh_fills IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM public.hypermesh_leases
      WHERE financial_activity_at IS NOT NULL OR financial_retain_until IS NOT NULL) THEN
      RAISE EXCEPTION 'Recorded Hypermesh financial clocks cannot be discarded';
    END IF; END $$""")
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM public.hypermesh_payouts
      WHERE financial_activity_at IS NOT NULL OR financial_retain_until IS NOT NULL) THEN
      RAISE EXCEPTION 'Recorded Hypermesh financial clocks cannot be discarded';
    END IF; END $$""")
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM public.hypermesh_orders
      WHERE financial_activity_at IS NOT NULL OR financial_retain_until IS NOT NULL) THEN
      RAISE EXCEPTION 'Recorded Hypermesh financial clocks cannot be discarded';
    END IF; END $$""")
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM public.hypermesh_fills
      WHERE financial_activity_at IS NOT NULL OR financial_retain_until IS NOT NULL) THEN
      RAISE EXCEPTION 'Recorded Hypermesh financial clocks cannot be discarded';
    END IF; END $$""")
    op.execute("DROP TRIGGER account_financial_epoch ON public.hypermesh_leases")
    op.execute(
        "DROP TRIGGER account_financial_not_truncated ON public.hypermesh_leases"
    )
    op.execute("DROP TRIGGER account_financial_epoch ON public.hypermesh_payouts")
    op.execute(
        "DROP TRIGGER account_financial_not_truncated ON public.hypermesh_payouts"
    )
    op.execute("DROP TRIGGER account_financial_epoch ON public.hypermesh_orders")
    op.execute(
        "DROP TRIGGER account_financial_not_truncated ON public.hypermesh_orders"
    )
    op.execute("DROP TRIGGER account_financial_epoch ON public.hypermesh_fills")
    op.execute("DROP TRIGGER account_financial_not_truncated ON public.hypermesh_fills")
    op.execute("DROP TRIGGER account_financial_epoch ON public.hypermesh_jobs")
    op.execute("DROP TRIGGER account_financial_not_truncated ON public.hypermesh_jobs")
    op.execute("DROP TRIGGER account_financial_epoch ON public.hypermesh_tunnels")
    op.execute(
        "DROP TRIGGER account_financial_not_truncated ON public.hypermesh_tunnels"
    )
    op.execute("DROP TRIGGER account_financial_epoch ON public.hypermesh_tickets")
    op.execute(
        "DROP TRIGGER account_financial_not_truncated ON public.hypermesh_tickets"
    )
    op.execute(
        "DROP TRIGGER account_financial_epoch ON public.host_organization_bindings"
    )
    op.execute(
        "DROP TRIGGER account_financial_not_truncated ON public.host_organization_bindings"
    )
    op.execute("DROP TRIGGER account_financial_clock ON public.hypermesh_leases")
    op.drop_index("ix_hypermesh_leases_financial_due", table_name="hypermesh_leases")
    op.drop_constraint(
        "ck_hypermesh_leases_financial_clock", "hypermesh_leases", type_="check"
    )
    op.drop_column("hypermesh_leases", "financial_retain_until")
    op.drop_column("hypermesh_leases", "financial_activity_at")
    op.execute("DROP TRIGGER account_financial_clock ON public.hypermesh_payouts")
    op.drop_index("ix_hypermesh_payouts_financial_due", table_name="hypermesh_payouts")
    op.drop_constraint(
        "ck_hypermesh_payouts_financial_clock", "hypermesh_payouts", type_="check"
    )
    op.drop_column("hypermesh_payouts", "financial_retain_until")
    op.drop_column("hypermesh_payouts", "financial_activity_at")
    op.execute("DROP TRIGGER account_financial_clock ON public.hypermesh_orders")
    op.drop_index("ix_hypermesh_orders_financial_due", table_name="hypermesh_orders")
    op.drop_constraint(
        "ck_hypermesh_orders_financial_clock", "hypermesh_orders", type_="check"
    )
    op.drop_column("hypermesh_orders", "financial_retain_until")
    op.drop_column("hypermesh_orders", "financial_activity_at")
    op.execute("DROP TRIGGER account_financial_clock ON public.hypermesh_fills")
    op.drop_index("ix_hypermesh_fills_financial_due", table_name="hypermesh_fills")
    op.drop_constraint(
        "ck_hypermesh_fills_financial_clock", "hypermesh_fills", type_="check"
    )
    op.drop_column("hypermesh_fills", "financial_retain_until")
    op.drop_column("hypermesh_fills", "financial_activity_at")
    op.execute("DROP FUNCTION public.hypermesh_account_financial_epoch()")
    op.execute("DROP FUNCTION public.hypermesh_financial_parties(text,jsonb)")
    op.execute("DROP FUNCTION public.hypermesh_financial_clock()")
