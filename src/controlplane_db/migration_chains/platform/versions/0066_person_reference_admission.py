"""Fence new operational profile links without deleting company resources."""

from alembic import op

revision = "platform_0066_person_references"
down_revision = "platform_0065_financial_epochs"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE FUNCTION public.platform_person_reference_admission()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog SET row_security=off AS $$
DECLARE subjects text[]; locked_subject text; current_sub text; active_profile boolean;
BEGIN
  IF TG_TABLE_NAME NOT IN ('crypto_agent_budgets','subscription_plans',
    'user_preferences','user_group_memberships','chat_sessions_ai') THEN
    RAISE EXCEPTION 'Unsupported personal reference admission' USING ERRCODE='42501';
  END IF;
  IF TG_OP='UPDATE' AND NEW.user_id IS NOT DISTINCT FROM OLD.user_id
    AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id THEN RETURN NEW; END IF;
  IF NEW.user_id IS NULL THEN RETURN NEW; END IF;
  IF current_setting('transaction_isolation')<>'read committed' THEN
    RAISE EXCEPTION 'Personal reference admission requires READ COMMITTED' USING ERRCODE='42501';
  END IF;
  subjects:=public.account_subjects_for_person(NEW.user_id);
  -- An outer INSERT/UPDATE can own a source row. Never wait for identity while
  -- holding that row; retirement/erasure can own identity and need the source.
  FOR locked_subject IN SELECT item FROM unnest(subjects) item
    ORDER BY hashtextextended('identity-retirement:'||item,0),item LOOP
    IF NOT pg_try_advisory_xact_lock(hashtextextended('identity-retirement:'||locked_subject,0)) THEN
      RAISE EXCEPTION 'Personal reference admission must retry' USING ERRCODE='40001';
    END IF;
  END LOOP;
  -- Directory deactivation also uses row locks without retirement locks.
  -- Stabilize and reread after identity admission; never wait while owning
  -- an outer source row or acquire a newly discovered identity out of order.
  BEGIN
    SELECT u.keycloak_sub,(u.is_active AND u.deleted_at IS NULL)
      INTO current_sub,active_profile FROM public.users u
      WHERE u.id=NEW.user_id FOR UPDATE NOWAIT;
    IF NOT FOUND OR NOT active_profile THEN
      RAISE EXCEPTION 'Account is unavailable' USING ERRCODE='42501';
    END IF;
  EXCEPTION WHEN lock_not_available THEN
    RAISE EXCEPTION 'Personal profile admission must retry' USING ERRCODE='40001';
  END;
  IF subjects IS DISTINCT FROM array_remove(ARRAY[NEW.user_id::text,current_sub],NULL) THEN
    RAISE EXCEPTION 'Personal identity binding changed; retry' USING ERRCODE='40001';
  END IF;
  PERFORM public.account_require_open_subjects(subjects);
  RETURN NEW;
END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.platform_person_reference_admission() FROM PUBLIC"
    )
    # Run before foreign-key checks can wait on a profile row held by erasure.
    # Existing-reference UPDATE maintenance returns before admission checks.
    op.execute(
        "CREATE TRIGGER account_person_reference_admission BEFORE INSERT OR UPDATE ON public.crypto_agent_budgets FOR EACH ROW EXECUTE FUNCTION public.platform_person_reference_admission()"
    )
    op.execute(
        "CREATE TRIGGER account_person_reference_admission BEFORE INSERT OR UPDATE ON public.subscription_plans FOR EACH ROW EXECUTE FUNCTION public.platform_person_reference_admission()"
    )
    op.execute(
        "CREATE TRIGGER account_person_reference_admission BEFORE INSERT OR UPDATE ON public.user_preferences FOR EACH ROW EXECUTE FUNCTION public.platform_person_reference_admission()"
    )
    op.execute(
        "CREATE TRIGGER account_person_reference_admission BEFORE INSERT OR UPDATE ON public.user_group_memberships FOR EACH ROW EXECUTE FUNCTION public.platform_person_reference_admission()"
    )
    op.execute(
        "CREATE TRIGGER account_person_reference_admission BEFORE INSERT OR UPDATE ON public.chat_sessions_ai FOR EACH ROW EXECUTE FUNCTION public.platform_person_reference_admission()"
    )


def downgrade():
    # Serialize the emptiness check with in-flight retirement and closure writes.
    # Retain these locks through all trigger removals in this transaction.
    op.execute(
        "LOCK TABLE public.identity_retirements, public.account_lifecycles, public.account_lifecycle_scopes, public.api_key_owner_closures IN SHARE MODE"
    )
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute(
        "DROP TRIGGER account_person_reference_admission ON public.crypto_agent_budgets"
    )
    op.execute(
        "DROP TRIGGER account_person_reference_admission ON public.subscription_plans"
    )
    op.execute(
        "DROP TRIGGER account_person_reference_admission ON public.user_preferences"
    )
    op.execute(
        "DROP TRIGGER account_person_reference_admission ON public.user_group_memberships"
    )
    op.execute(
        "DROP TRIGGER account_person_reference_admission ON public.chat_sessions_ai"
    )
    op.execute("DROP FUNCTION public.platform_person_reference_admission()")
