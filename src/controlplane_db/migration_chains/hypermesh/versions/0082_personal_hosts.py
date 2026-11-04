"""Erase host-person associations while retaining company installation state."""

from alembic import op

revision = "hypermesh_0082_personal_hosts"
down_revision = "hypermesh_0081_fin_inventory"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    # Require the personal scope capability before changing admission.
    op.execute("""DO $$ BEGIN
      IF to_regprocedure('public.account_require_personal_erasure(text,uuid)') IS NULL THEN
        RAISE EXCEPTION 'Native personal erasure scope is not installed';
      END IF;
    END $$""")
    op.execute("""CREATE OR REPLACE FUNCTION public.hypermesh_account_admission()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
    DECLARE actors text[] := ARRAY[]::text[]; host uuid; resolved_host uuid; renter uuid; owner_sub text;
    BEGIN
      IF TG_TABLE_NAME='hypermesh_host_registrations' AND TG_OP='UPDATE' THEN
        IF OLD.owner_sub='closed-installation:'||OLD.id::text THEN
          IF NEW.owner_sub IS DISTINCT FROM OLD.owner_sub
            OR NEW.id IS DISTINCT FROM OLD.id OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
            OR NEW.host_org_id IS DISTINCT FROM OLD.host_org_id OR NEW.device_id IS DISTINCT FROM OLD.device_id
            OR NEW.request ? '_owner_membership' THEN
            RAISE EXCEPTION 'Erased installation identity cannot be reassigned' USING ERRCODE='42501';
          END IF;
        ELSIF NEW.owner_sub='closed-installation:'||OLD.id::text
          AND jsonb_typeof(OLD.request)='object'
          AND NEW.request=OLD.request-'_owner_membership'
          AND (to_jsonb(NEW)-ARRAY['owner_sub','request']) IS NOT DISTINCT FROM
              (to_jsonb(OLD)-ARRAY['owner_sub','request']) THEN
          PERFORM public.account_require_personal_erasure(OLD.owner_sub,OLD.tenant_id);
          RETURN NEW;
        END IF;
      END IF;
      IF TG_OP='DELETE' AND TG_TABLE_NAME='host_organization_bindings' THEN
        IF OLD.keycloak_sub LIKE 'apikey:%' OR length(btrim(OLD.keycloak_sub))=0 THEN
          RAISE EXCEPTION 'Canonical host binding identity required' USING ERRCODE='42501';
        END IF;
        IF NOT pg_try_advisory_xact_lock(hashtextextended('identity-retirement:'||OLD.keycloak_sub,0)) THEN
          RAISE EXCEPTION 'Host association removal must retry' USING ERRCODE='40001';
        END IF;
        BEGIN
          PERFORM public.account_require_open_subjects(ARRAY[OLD.keycloak_sub]);
        EXCEPTION WHEN insufficient_privilege THEN
          -- Ordinary removal stays available to open accounts. A retired
          -- identity needs the complete native personal cleanup authority.
          BEGIN
            PERFORM public.account_require_personal_erasure(OLD.keycloak_sub,OLD.tenant_id);
          EXCEPTION WHEN insufficient_privilege THEN
            RAISE EXCEPTION 'Account is unavailable' USING ERRCODE='42501';
          END;
        END;
        RETURN OLD;
      END IF;
      IF TG_OP='UPDATE' AND NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
        RAISE EXCEPTION 'Account resource scope cannot be reassigned' USING ERRCODE='42501';
      END IF;
      IF TG_TABLE_NAME='hypermesh_leases' THEN
        IF TG_OP='UPDATE' AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id
          AND NEW.renter_user_id IS NOT DISTINCT FROM OLD.renter_user_id
          AND NEW.device_id IS NOT DISTINCT FROM OLD.device_id
          AND NEW.host_org_id IS NOT DISTINCT FROM OLD.host_org_id
          AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at
          AND NOT (NEW.status='offered' AND OLD.status<>'offered')
          -- Paying or starting an outstanding offer is new host authority,
          -- even when ownership and created_at stay the same. Maintenance of
          -- work already paid before retirement still returns above.
          AND NOT (OLD.status='offered' AND NEW.status IN ('paid','starting','active'))
          AND NOT (OLD.status IN ('failed','expired','ended','refunded')
                   AND NEW.status IN ('paid','starting','active')) THEN RETURN NEW; END IF;
        actors := public.account_subjects_for_person(NEW.renter_user_id);
        IF TG_OP='UPDATE' THEN
          actors := actors || public.account_subjects_for_person(OLD.renter_user_id);
          SELECT keycloak_sub INTO owner_sub FROM public.host_organization_bindings
            WHERE tenant_id=OLD.tenant_id AND organization_id=coalesce(OLD.host_org_id,
              (SELECT host_org_id FROM public.hypermesh_devices WHERE id=OLD.device_id AND tenant_id=OLD.tenant_id));
          actors := array_append(actors,owner_sub);
        END IF;
        host := NEW.host_org_id;
        IF NEW.device_id IS NOT NULL THEN
          SELECT host_org_id INTO resolved_host FROM public.hypermesh_devices
            WHERE id=NEW.device_id AND tenant_id=NEW.tenant_id;
          -- Legacy/financial rows may reference a device no longer stored.
          -- Preserve their explicit host attribution; do not invent ownership
          -- or turn this retirement fence into a new device foreign key.
          IF FOUND THEN
            IF NEW.host_org_id IS NOT NULL AND NEW.host_org_id<>resolved_host THEN
              RAISE EXCEPTION 'Account host authority unavailable' USING ERRCODE='42501';
            END IF;
            host := resolved_host;
          END IF;
        END IF;
      ELSIF TG_TABLE_NAME='hypermesh_tickets' THEN
        IF TG_OP='UPDATE' AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id
          AND NEW.lease_id IS NOT DISTINCT FROM OLD.lease_id
          AND NEW.ticket IS NOT DISTINCT FROM OLD.ticket AND NEW.exp<=OLD.exp
          AND NOT (NEW.status='active' AND OLD.status<>'active') THEN RETURN NEW; END IF;
        SELECT renter_user_id INTO renter FROM public.hypermesh_leases
          WHERE id=NEW.lease_id AND tenant_id=NEW.tenant_id;
        IF NOT FOUND THEN RAISE EXCEPTION 'Account lease authority unavailable' USING ERRCODE='42501'; END IF;
        -- Host retirement must not prevent another renter's existing lease
        -- from renewing its ticket and finishing normally.
        actors := public.account_subjects_for_person(renter);
        IF TG_OP='UPDATE' AND NEW.lease_id IS DISTINCT FROM OLD.lease_id THEN
          SELECT renter_user_id INTO renter FROM public.hypermesh_leases
            WHERE id=OLD.lease_id AND tenant_id=OLD.tenant_id;
          IF NOT FOUND THEN RAISE EXCEPTION 'Account lease authority unavailable' USING ERRCODE='42501'; END IF;
          actors := actors || public.account_subjects_for_person(renter);
        END IF;
      ELSIF TG_TABLE_NAME='hypermesh_devices' THEN
        IF TG_OP='UPDATE' AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id
          AND NEW.host_org_id IS NOT DISTINCT FROM OLD.host_org_id
          AND NOT (OLD.archived_at IS NOT NULL AND NEW.archived_at IS NULL)
          AND NOT (NEW.enrolled AND NOT OLD.enrolled)
          AND NEW.sell_state IS NOT DISTINCT FROM OLD.sell_state THEN RETURN NEW; END IF;
        -- Turning selling off and ordinary heartbeat/runtime maintenance do
        -- not grant new authority. Host-peer/runtime state stays intact.
        IF TG_OP='UPDATE' AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id
          AND NEW.host_org_id IS NOT DISTINCT FROM OLD.host_org_id
          AND (NEW.archived_at IS NOT NULL OR OLD.archived_at IS NULL)
          AND NOT (NEW.enrolled AND NOT OLD.enrolled)
          AND NEW.sell_state IN ('n/a','paused','off','draining') THEN RETURN NEW; END IF;
        host := NEW.host_org_id;
        IF TG_OP='UPDATE' THEN
          SELECT keycloak_sub INTO owner_sub FROM public.host_organization_bindings
            WHERE tenant_id=OLD.tenant_id AND organization_id=OLD.host_org_id;
          actors := array_append(actors,owner_sub);
        END IF;
      ELSIF TG_TABLE_NAME='host_organization_bindings' THEN
        IF TG_OP='UPDATE' AND NEW IS NOT DISTINCT FROM OLD THEN RETURN NEW; END IF;
        actors := ARRAY[NEW.keycloak_sub];
        IF TG_OP='UPDATE' THEN actors := array_append(actors,OLD.keycloak_sub); END IF;
      ELSIF TG_TABLE_NAME IN ('hypermesh_model_revisions','hypermesh_model_validations','hypermesh_host_registrations') THEN
        IF TG_OP='UPDATE' AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id
          AND NEW.owner_sub IS NOT DISTINCT FROM OLD.owner_sub THEN RETURN NEW; END IF;
        actors := ARRAY[NEW.owner_sub];
        IF TG_OP='UPDATE' THEN actors := array_append(actors,OLD.owner_sub); END IF;
      ELSE
        RAISE EXCEPTION 'Unsupported Hypermesh account admission context';
      END IF;
      IF host IS NOT NULL THEN
        SELECT keycloak_sub INTO owner_sub FROM public.host_organization_bindings
          WHERE tenant_id=NEW.tenant_id AND organization_id=host;
        -- Only exact default-org ownership proves this is a person's host.
        -- A generic membership never transfers ownership of a company host.
        actors := array_append(actors,owner_sub);
      END IF;
      PERFORM public.account_require_open_subjects(actors);
      RETURN NEW;
    END $$""")
    op.execute("""CREATE FUNCTION public.hypermesh_erase_personal_host_associations(
      p_subject text,p_closed_at timestamptz,p_tenant uuid,p_limit integer DEFAULT 100)
    RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE item record; processed integer:=0; remaining bigint; affected integer;
    BEGIN
      PERFORM public.account_lock_financial_inventory(p_subject,p_closed_at,p_tenant);
      PERFORM public.account_require_personal_erasure(p_subject,p_tenant);
      IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 1000 THEN
        RAISE EXCEPTION 'Bounded personal association batch required' USING ERRCODE='42501';
      END IF;
      IF EXISTS(SELECT 1 FROM public.hypermesh_host_registrations
        WHERE tenant_id=p_tenant AND owner_sub=p_subject AND jsonb_typeof(request)<>'object') THEN
        RAISE EXCEPTION 'Installation metadata requires reconciliation' USING ERRCODE='42501';
      END IF;
      -- These associations are personal authority, not company/device ownership.
      DELETE FROM public.host_organization_bindings WHERE tenant_id=p_tenant AND keycloak_sub=p_subject;
      GET DIAGNOSTICS affected=ROW_COUNT;
      processed:=processed+affected;
      FOR item IN SELECT id FROM public.hypermesh_host_registrations
        WHERE tenant_id=p_tenant AND owner_sub=p_subject ORDER BY id LIMIT p_limit FOR UPDATE NOWAIT LOOP
        UPDATE public.hypermesh_host_registrations
          SET owner_sub='closed-installation:'||id::text,request=request-'_owner_membership' WHERE id=item.id;
        processed:=processed+1;
      END LOOP;
      FOR item IN SELECT id FROM public.hypermesh_onboarding_runs
        WHERE tenant_id=p_tenant AND approved_by=p_subject ORDER BY id LIMIT p_limit FOR UPDATE NOWAIT LOOP
        -- Lab decisions are durable business facts; only resume approvals expire.
        UPDATE public.hypermesh_onboarding_runs SET approved_by=NULL,
          approved_at=CASE WHEN manifest->>'purpose'='lab-qualification-v1'
            THEN approved_at ELSE NULL END WHERE id=item.id;
        processed:=processed+1;
      END LOOP;
      PERFORM public.account_unbind_hypermesh_personal_sources(p_subject,p_tenant);
      SELECT (SELECT count(*) FROM public.host_organization_bindings WHERE tenant_id=p_tenant AND keycloak_sub=p_subject)
        +(SELECT count(*) FROM public.hypermesh_host_registrations WHERE tenant_id=p_tenant AND owner_sub=p_subject)
        +(SELECT count(*) FROM public.hypermesh_onboarding_runs WHERE tenant_id=p_tenant AND approved_by=p_subject)
        INTO remaining;
      RETURN jsonb_build_object('complete',remaining=0,'processed',processed,'remaining',remaining);
    EXCEPTION WHEN lock_not_available THEN
      RAISE EXCEPTION 'Personal association transaction must retry' USING ERRCODE='40001';
    END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.hypermesh_erase_personal_host_associations(text,timestamptz,uuid,integer) FROM PUBLIC"
    )

    op.execute("""CREATE FUNCTION public.hypermesh_personal_approval_admission()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    BEGIN
      IF NEW.approved_by IS NULL THEN RETURN NEW; END IF;
      IF TG_OP='UPDATE' AND NEW.approved_by IS NOT DISTINCT FROM OLD.approved_by
        AND (NEW.approved_at IS NULL OR NEW.approved_at IS NOT DISTINCT FROM OLD.approved_at) THEN
        RETURN NEW;
      END IF;
      IF length(btrim(NEW.approved_by))=0 OR NEW.approved_by LIKE 'apikey:%' THEN
        RAISE EXCEPTION 'Canonical approval identity required' USING ERRCODE='42501';
      END IF;
      IF NOT pg_try_advisory_xact_lock(hashtextextended('identity-retirement:'||NEW.approved_by,0)) THEN
        RAISE EXCEPTION 'Approval admission must retry' USING ERRCODE='40001';
      END IF;
      PERFORM public.account_require_open_subjects(ARRAY[NEW.approved_by]);
      RETURN NEW;
    END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.hypermesh_personal_approval_admission() FROM PUBLIC"
    )
    op.execute(
        "CREATE TRIGGER account_approval_admission BEFORE INSERT OR UPDATE ON public.hypermesh_onboarding_runs FOR EACH ROW EXECUTE FUNCTION public.hypermesh_personal_approval_admission()"
    )


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute(
        "DROP TRIGGER account_approval_admission ON public.hypermesh_onboarding_runs"
    )
    op.execute("DROP FUNCTION public.hypermesh_personal_approval_admission()")
    op.execute(
        "DROP FUNCTION public.hypermesh_erase_personal_host_associations(text,timestamptz,uuid,integer)"
    )
    op.execute("""CREATE OR REPLACE FUNCTION public.hypermesh_account_admission()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
    DECLARE actors text[] := ARRAY[]::text[]; host uuid; resolved_host uuid; renter uuid; owner_sub text;
    BEGIN
      IF TG_OP='DELETE' AND TG_TABLE_NAME='host_organization_bindings' THEN
        PERFORM public.account_require_open_subjects(ARRAY[OLD.keycloak_sub]);
        RETURN OLD;
      END IF;
      IF TG_OP='UPDATE' AND NEW.tenant_id IS DISTINCT FROM OLD.tenant_id THEN
        RAISE EXCEPTION 'Account resource scope cannot be reassigned' USING ERRCODE='42501';
      END IF;
      IF TG_TABLE_NAME='hypermesh_leases' THEN
        IF TG_OP='UPDATE' AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id
          AND NEW.renter_user_id IS NOT DISTINCT FROM OLD.renter_user_id
          AND NEW.device_id IS NOT DISTINCT FROM OLD.device_id
          AND NEW.host_org_id IS NOT DISTINCT FROM OLD.host_org_id
          AND NEW.created_at IS NOT DISTINCT FROM OLD.created_at
          AND NOT (NEW.status='offered' AND OLD.status<>'offered')
          -- Paying or starting an outstanding offer is new host authority,
          -- even when ownership and created_at stay the same. Maintenance of
          -- work already paid before retirement still returns above.
          AND NOT (OLD.status='offered' AND NEW.status IN ('paid','starting','active'))
          AND NOT (OLD.status IN ('failed','expired','ended','refunded')
                   AND NEW.status IN ('paid','starting','active')) THEN RETURN NEW; END IF;
        actors := public.account_subjects_for_person(NEW.renter_user_id);
        IF TG_OP='UPDATE' THEN
          actors := actors || public.account_subjects_for_person(OLD.renter_user_id);
          SELECT keycloak_sub INTO owner_sub FROM public.host_organization_bindings
            WHERE tenant_id=OLD.tenant_id AND organization_id=coalesce(OLD.host_org_id,
              (SELECT host_org_id FROM public.hypermesh_devices WHERE id=OLD.device_id AND tenant_id=OLD.tenant_id));
          actors := array_append(actors,owner_sub);
        END IF;
        host := NEW.host_org_id;
        IF NEW.device_id IS NOT NULL THEN
          SELECT host_org_id INTO resolved_host FROM public.hypermesh_devices
            WHERE id=NEW.device_id AND tenant_id=NEW.tenant_id;
          -- Legacy/financial rows may reference a device no longer stored.
          -- Preserve their explicit host attribution; do not invent ownership
          -- or turn this retirement fence into a new device foreign key.
          IF FOUND THEN
            IF NEW.host_org_id IS NOT NULL AND NEW.host_org_id<>resolved_host THEN
              RAISE EXCEPTION 'Account host authority unavailable' USING ERRCODE='42501';
            END IF;
            host := resolved_host;
          END IF;
        END IF;
      ELSIF TG_TABLE_NAME='hypermesh_tickets' THEN
        IF TG_OP='UPDATE' AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id
          AND NEW.lease_id IS NOT DISTINCT FROM OLD.lease_id
          AND NEW.ticket IS NOT DISTINCT FROM OLD.ticket AND NEW.exp<=OLD.exp
          AND NOT (NEW.status='active' AND OLD.status<>'active') THEN RETURN NEW; END IF;
        SELECT renter_user_id INTO renter FROM public.hypermesh_leases
          WHERE id=NEW.lease_id AND tenant_id=NEW.tenant_id;
        IF NOT FOUND THEN RAISE EXCEPTION 'Account lease authority unavailable' USING ERRCODE='42501'; END IF;
        -- Host retirement must not prevent another renter's existing lease
        -- from renewing its ticket and finishing normally.
        actors := public.account_subjects_for_person(renter);
        IF TG_OP='UPDATE' AND NEW.lease_id IS DISTINCT FROM OLD.lease_id THEN
          SELECT renter_user_id INTO renter FROM public.hypermesh_leases
            WHERE id=OLD.lease_id AND tenant_id=OLD.tenant_id;
          IF NOT FOUND THEN RAISE EXCEPTION 'Account lease authority unavailable' USING ERRCODE='42501'; END IF;
          actors := actors || public.account_subjects_for_person(renter);
        END IF;
      ELSIF TG_TABLE_NAME='hypermesh_devices' THEN
        IF TG_OP='UPDATE' AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id
          AND NEW.host_org_id IS NOT DISTINCT FROM OLD.host_org_id
          AND NOT (OLD.archived_at IS NOT NULL AND NEW.archived_at IS NULL)
          AND NOT (NEW.enrolled AND NOT OLD.enrolled)
          AND NEW.sell_state IS NOT DISTINCT FROM OLD.sell_state THEN RETURN NEW; END IF;
        -- Turning selling off and ordinary heartbeat/runtime maintenance do
        -- not grant new authority. Host-peer/runtime state stays intact.
        IF TG_OP='UPDATE' AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id
          AND NEW.host_org_id IS NOT DISTINCT FROM OLD.host_org_id
          AND (NEW.archived_at IS NOT NULL OR OLD.archived_at IS NULL)
          AND NOT (NEW.enrolled AND NOT OLD.enrolled)
          AND NEW.sell_state IN ('n/a','paused','off','draining') THEN RETURN NEW; END IF;
        host := NEW.host_org_id;
        IF TG_OP='UPDATE' THEN
          SELECT keycloak_sub INTO owner_sub FROM public.host_organization_bindings
            WHERE tenant_id=OLD.tenant_id AND organization_id=OLD.host_org_id;
          actors := array_append(actors,owner_sub);
        END IF;
      ELSIF TG_TABLE_NAME='host_organization_bindings' THEN
        IF TG_OP='UPDATE' AND NEW IS NOT DISTINCT FROM OLD THEN RETURN NEW; END IF;
        actors := ARRAY[NEW.keycloak_sub];
        IF TG_OP='UPDATE' THEN actors := array_append(actors,OLD.keycloak_sub); END IF;
      ELSIF TG_TABLE_NAME IN ('hypermesh_model_revisions','hypermesh_model_validations','hypermesh_host_registrations') THEN
        IF TG_OP='UPDATE' AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id
          AND NEW.owner_sub IS NOT DISTINCT FROM OLD.owner_sub THEN RETURN NEW; END IF;
        actors := ARRAY[NEW.owner_sub];
        IF TG_OP='UPDATE' THEN actors := array_append(actors,OLD.owner_sub); END IF;
      ELSE
        RAISE EXCEPTION 'Unsupported Hypermesh account admission context';
      END IF;
      IF host IS NOT NULL THEN
        SELECT keycloak_sub INTO owner_sub FROM public.host_organization_bindings
          WHERE tenant_id=NEW.tenant_id AND organization_id=host;
        -- Only exact default-org ownership proves this is a person's host.
        -- A generic membership never transfers ownership of a company host.
        actors := array_append(actors,owner_sub);
      END IF;
      PERFORM public.account_require_open_subjects(actors);
      RETURN NEW;
    END $$""")
