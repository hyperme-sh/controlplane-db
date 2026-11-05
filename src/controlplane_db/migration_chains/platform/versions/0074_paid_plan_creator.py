"""Keep paid company projection without restoring a retired optional creator."""

from alembic import op

revision = "platform_0074_paid_creator"
down_revision = "platform_0073_access_actor"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""CREATE FUNCTION public.account_paid_plan_creator()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE subjects text[]; historical text[]; candidate text; profile record; retired boolean;
    BEGIN
      IF NEW.user_id IS NULL OR NEW.tenant_id IS NULL THEN RETURN NEW; END IF;
      IF TG_OP='UPDATE' THEN
        IF NEW.user_id IS NOT DISTINCT FROM OLD.user_id AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id THEN
          RETURN NEW;
        END IF;
        IF NEW.id IS DISTINCT FROM OLD.id OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
          OR NEW.actor IS DISTINCT FROM OLD.actor THEN RETURN NEW; END IF;
      END IF;
      IF NEW.is_trial OR NOT (NEW.actor IN ('tenant','payment') OR (TG_OP='UPDATE' AND EXISTS(
        SELECT 1 FROM public.tenants WHERE id=NEW.tenant_id AND subscription_id=OLD.id))) THEN RETURN NEW; END IF;
      IF current_setting('transaction_isolation')<>'read committed' THEN
        RAISE EXCEPTION 'Creator projection requires READ COMMITTED' USING ERRCODE='42501';
      END IF;
      BEGIN
        LOCK TABLE public.account_financial_fence_versions IN SHARE MODE NOWAIT;
      EXCEPTION WHEN lock_not_available THEN
        RAISE EXCEPTION 'Creator projection must retry' USING ERRCODE='40001';
      END;
      -- Ordinary admission rejects inactive profiles. Here the only possible
      -- outcome is omitting optional metadata, so read a snapshot without
      -- treating an erased profile as eligible for a new reference.
      SELECT array_remove(ARRAY[NEW.user_id::text,u.keycloak_sub],NULL) INTO subjects
        FROM public.users u WHERE u.id=NEW.user_id;
      IF NOT FOUND THEN RETURN NEW; END IF;
      SELECT coalesce(array_agg(DISTINCT p.subject),ARRAY[]::text[]) INTO historical
        FROM public.account_financial_parties(NEW.user_id,NULL,NEW.tenant_id) p WHERE p.direct_reference;
      FOR candidate IN SELECT value FROM (SELECT DISTINCT value FROM unnest(subjects||historical) value) candidates
        ORDER BY hashtextextended('identity-retirement:'||value,0),value LOOP
        IF NOT pg_try_advisory_xact_lock(hashtextextended('identity-retirement:'||candidate,0)) THEN
          RAISE EXCEPTION 'Creator identity must retry' USING ERRCODE='40001';
        END IF;
      END LOOP;
      BEGIN
        SELECT keycloak_sub,is_active,deleted_at,email INTO profile FROM public.users WHERE id=NEW.user_id FOR UPDATE NOWAIT;
      EXCEPTION WHEN lock_not_available THEN
        RAISE EXCEPTION 'Creator profile must retry' USING ERRCODE='40001';
      END;
      IF NOT FOUND THEN RETURN NEW; END IF;
      IF subjects IS DISTINCT FROM array_remove(ARRAY[NEW.user_id::text,profile.keycloak_sub],NULL) THEN
        RAISE EXCEPTION 'Creator identity changed; retry' USING ERRCODE='40001';
      END IF;
      SELECT EXISTS(SELECT 1 FROM public.identity_retirements WHERE subject=profile.keycloak_sub) INTO retired;
      IF NOT retired AND profile.keycloak_sub IS NULL AND NOT profile.is_active
        AND profile.deleted_at IS NOT NULL AND profile.email ~ '^closed[+][a-z2-7]{52}@account[.]invalid$' THEN
        -- Only a unique original profile inventory can identify an erased stub.
        SELECT coalesce(array_agg(DISTINCT p.subject),ARRAY[]::text[]) INTO historical
          FROM public.account_financial_parties(NEW.user_id,NULL,NEW.tenant_id) p
          JOIN public.identity_retirements i ON i.subject=p.subject WHERE p.direct_reference;
        retired:=cardinality(historical)=1;
      END IF;
      -- This never authorizes a payment, changes a tier, or guesses its payer.
      -- It drops only new optional creator metadata for a company's paid effect.
      IF retired AND EXISTS(SELECT 1 FROM public.billing_records
          WHERE tenant_id=NEW.tenant_id AND user_id=NEW.user_id AND scope='invoice'
            AND payment_type='stripe_invoice' AND status='succeeded') THEN
        IF TG_OP='UPDATE' THEN NEW.user_id:=OLD.user_id; ELSE NEW.user_id:=NULL; END IF;
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_paid_plan_creator() FROM PUBLIC")
    # Runs before ordinary reference admission; unsupported links still meet its
    # original rejection path. The new projection keeps no retired-user reference.
    op.execute("""CREATE TRIGGER aaa_paid_plan_creator BEFORE INSERT OR UPDATE ON public.subscription_plans
      FOR EACH ROW EXECUTE FUNCTION public.account_paid_plan_creator()""")


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("DROP TRIGGER aaa_paid_plan_creator ON public.subscription_plans")
    op.execute("DROP FUNCTION public.account_paid_plan_creator()")
