"""Fence new Hypermesh authority while allowing running leases to finish."""
from alembic import op

revision = "hypermesh_0078_account_admission"
down_revision = "hypermesh_0078_cert_evidence"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""DO $$ BEGIN
      IF to_regprocedure('public.account_require_open_subjects(text[])') IS NULL
        OR to_regprocedure('public.account_subjects_for_person(uuid)') IS NULL THEN
        RAISE EXCEPTION 'Platform account admission revision 0060 is required';
      END IF;
    END $$""")
    op.execute("""CREATE FUNCTION public.hypermesh_account_admission()
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
    op.execute("REVOKE ALL ON FUNCTION public.hypermesh_account_admission() FROM PUBLIC")
    for table in (
        "hypermesh_leases", "hypermesh_tickets", "hypermesh_devices",
        "host_organization_bindings", "hypermesh_model_revisions",
        "hypermesh_model_validations", "hypermesh_host_registrations",
    ):
        op.execute(f"CREATE TRIGGER account_admission AFTER INSERT OR UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION public.hypermesh_account_admission()")
    op.execute("""CREATE TRIGGER account_owner_delete BEFORE DELETE ON host_organization_bindings
        FOR EACH ROW EXECUTE FUNCTION public.hypermesh_account_admission()""")


def downgrade():
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("DROP TRIGGER account_owner_delete ON host_organization_bindings")
    for table in (
        "hypermesh_leases", "hypermesh_tickets", "hypermesh_devices",
        "host_organization_bindings", "hypermesh_model_revisions",
        "hypermesh_model_validations", "hypermesh_host_registrations",
    ):
        op.execute(f"DROP TRIGGER account_admission ON {table}")
    op.execute("DROP FUNCTION public.hypermesh_account_admission()")
