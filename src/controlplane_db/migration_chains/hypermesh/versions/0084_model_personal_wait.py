"""Honor trusted personal erasure authorization while retaining every model guard."""

from alembic import op

revision = "hypermesh_0084_model_wait"
down_revision = "hypermesh_0083_personal_runtime"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""DO $$ BEGIN
      IF to_regprocedure('public.account_personal_model_erasure_allowed(text,uuid,timestamptz)') IS NULL THEN
        RAISE EXCEPTION 'Trusted personal model authorization is not installed';
      END IF;
    END $$""")
    op.execute("""CREATE FUNCTION public.hypermesh_personal_model_wait(
      p_subject text,p_tenant uuid,p_model_closed_at timestamptz)
    RETURNS boolean LANGUAGE sql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
      SELECT public.account_personal_model_erasure_allowed(p_subject,p_tenant,p_model_closed_at)
    $$""")
    op.execute("REVOKE ALL ON FUNCTION public.hypermesh_personal_model_wait(text,uuid,timestamptz) FROM PUBLIC")
    op.execute("""CREATE OR REPLACE FUNCTION public.hypermesh_private_lease_pin_immutable()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE cleanup_ack jsonb; record_created_at timestamptz;
    BEGIN
      IF OLD.private_model IS NOT NULL AND NEW.private_model IS DISTINCT FROM OLD.private_model THEN
        IF NEW.private_model IS NOT NULL
          AND OLD.private_model ? 'target'
          AND NEW.private_model = OLD.private_model - 'target'
          AND to_jsonb(NEW) - 'private_model' = to_jsonb(OLD) - 'private_model'
          AND OLD.status IN ('offered','ended','failed','refunded') THEN
          SELECT jsonb_path_query_first(r.lifecycle_audit,
            '$[*] ? (@.actor == "operations" && @.action == "deleted" && @.reason == "Exact version inventory has no live blobs")'), r.created_at
            INTO cleanup_ack, record_created_at
            FROM public.hypermesh_model_validations v
            JOIN public.hypermesh_model_revisions r ON r.id=v.revision_id AND r.tenant_id=v.tenant_id
            JOIN public.hypermesh_model_owner_closures c ON c.tenant_id=r.tenant_id AND c.owner_sub=r.owner_sub
            WHERE v.id=(OLD.private_model->>'validation_id')::uuid
              AND v.tenant_id=OLD.tenant_id AND v.target_sha256=OLD.private_model->>'target_sha256'
              AND v.owner_sub=r.owner_sub AND r.state='deleted' AND NOT r.retention_hold
              AND (r.retain_until IS NULL OR r.retain_until <= clock_timestamp())
              AND (c.closed_at <= clock_timestamp() - interval '89 days'
                OR public.hypermesh_personal_model_wait(r.owner_sub,r.tenant_id,c.closed_at))
              AND r.lifecycle_audit @> '[{"actor":"operations","action":"deleted","reason":"Exact version inventory has no live blobs"}]'::jsonb
              AND jsonb_typeof(r.lifecycle_audit)='array'
            FOR SHARE OF v,r,c;
          IF FOUND AND (cleanup_ack->>'at') ~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
            AND (cleanup_ack->>'at')::timestamptz >= record_created_at
            AND (cleanup_ack->>'at')::timestamptz <= clock_timestamp()
          THEN RETURN NEW; END IF;
        END IF;
        RAISE EXCEPTION 'Private lease model pin is immutable';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.hypermesh_private_lease_pin_immutable() FROM PUBLIC")


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("""CREATE OR REPLACE FUNCTION public.hypermesh_private_lease_pin_immutable()
    RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
    DECLARE cleanup_ack jsonb; record_created_at timestamptz;
    BEGIN
      IF OLD.private_model IS NOT NULL AND NEW.private_model IS DISTINCT FROM OLD.private_model THEN
        IF NEW.private_model IS NOT NULL
          AND OLD.private_model ? 'target'
          AND NEW.private_model = OLD.private_model - 'target'
          AND to_jsonb(NEW) - 'private_model' = to_jsonb(OLD) - 'private_model'
          AND OLD.status IN ('offered','ended','failed','refunded') THEN
          SELECT jsonb_path_query_first(r.lifecycle_audit,
            '$[*] ? (@.actor == "operations" && @.action == "deleted" && @.reason == "Exact version inventory has no live blobs")'), r.created_at
            INTO cleanup_ack, record_created_at
            FROM public.hypermesh_model_validations v
            JOIN public.hypermesh_model_revisions r ON r.id=v.revision_id AND r.tenant_id=v.tenant_id
            JOIN public.hypermesh_model_owner_closures c ON c.tenant_id=r.tenant_id AND c.owner_sub=r.owner_sub
            WHERE v.id=(OLD.private_model->>'validation_id')::uuid
              AND v.tenant_id=OLD.tenant_id AND v.target_sha256=OLD.private_model->>'target_sha256'
              AND v.owner_sub=r.owner_sub AND r.state='deleted' AND NOT r.retention_hold
              AND (r.retain_until IS NULL OR r.retain_until <= clock_timestamp())
              AND c.closed_at <= clock_timestamp() - interval '89 days'
              AND r.lifecycle_audit @> '[{"actor":"operations","action":"deleted","reason":"Exact version inventory has no live blobs"}]'::jsonb
              AND jsonb_typeof(r.lifecycle_audit)='array'
            FOR SHARE OF v,r,c;
          IF FOUND AND (cleanup_ack->>'at') ~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
            AND (cleanup_ack->>'at')::timestamptz >= record_created_at
            AND (cleanup_ack->>'at')::timestamptz <= clock_timestamp()
          THEN RETURN NEW; END IF;
        END IF;
        RAISE EXCEPTION 'Private lease model pin is immutable';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("GRANT EXECUTE ON FUNCTION public.hypermesh_private_lease_pin_immutable() TO PUBLIC")
    op.execute("DROP FUNCTION public.hypermesh_personal_model_wait(text,uuid,timestamptz)")
