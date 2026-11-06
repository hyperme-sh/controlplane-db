"""Serialize financial destruction with explicitly accepted preservation holds."""

from alembic import op

revision = "platform_0061_financial_guard"
down_revision = "platform_0060_account_admission"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE FUNCTION public.account_lock_financial_erasure(
        p_subject text, p_closed_at timestamptz, p_tenant_id uuid DEFAULT NULL)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    BEGIN
      IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'Financial erasure requires READ COMMITTED isolation' USING ERRCODE='42501';
      END IF;
      IF p_subject IS NULL OR length(btrim(p_subject))=0
        OR length(p_subject)>512 OR p_subject LIKE 'apikey:%'
        OR p_closed_at IS NULL THEN
        RAISE EXCEPTION 'Financial erasure authority unavailable' USING ERRCODE='42501';
      END IF;
      PERFORM pg_advisory_xact_lock(hashtextextended('identity-retirement:'||p_subject,0));
      IF NOT EXISTS (
        SELECT 1 FROM public.account_lifecycles a
        JOIN public.identity_retirements i ON i.subject=a.subject
        WHERE a.subject=p_subject AND a.closed_at=p_closed_at
          AND i.retired_at<=a.closed_at AND NOT a.financial_hold
          AND a.state IN ('closed','deleting','deleted')
          AND a.effects @> '{"identity": {"disabled": true}}'::jsonb
          AND (
            (p_tenant_id IS NULL
              AND jsonb_typeof(a.effects->'platform_profile'->'user_ids')='array')
            OR (p_tenant_id IS NOT NULL AND EXISTS (
              SELECT 1 FROM public.account_lifecycle_scopes s
              WHERE s.subject=a.subject AND s.tenant_id=p_tenant_id
                AND s.effects @> '{"profile_inventory_complete": true}'::jsonb
            ))
          )
      ) THEN
        RAISE EXCEPTION 'Financial erasure authority unavailable' USING ERRCODE='42501';
      END IF;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_lock_financial_erasure(text,timestamptz,uuid) FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.account_serialize_financial_hold()
    RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
    BEGIN
      IF NEW.financial_hold IS DISTINCT FROM OLD.financial_hold
        OR NEW.hold_reference IS DISTINCT FROM OLD.hold_reference THEN
        IF NEW.subject IS DISTINCT FROM OLD.subject THEN
          RAISE EXCEPTION 'Financial preservation subject cannot be replaced';
        END IF;
        PERFORM pg_advisory_xact_lock(hashtextextended('identity-retirement:'||OLD.subject,0));
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_serialize_financial_hold() FROM PUBLIC")
    op.execute("""CREATE TRIGGER account_financial_hold_serialized
      BEFORE UPDATE ON public.account_lifecycles
      FOR EACH ROW EXECUTE FUNCTION public.account_serialize_financial_hold()""")


def downgrade():
    # Even rows hidden by RLS must prevent discarding an accepted hold fence.
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("DROP TRIGGER account_financial_hold_serialized ON public.account_lifecycles")
    op.execute("DROP FUNCTION public.account_serialize_financial_hold()")
    op.execute("DROP FUNCTION public.account_lock_financial_erasure(text,timestamptz,uuid)")
