"""Fence auth artifacts and snapshot isolation against identity retirement."""

from alembic import op

revision = "platform_0064_auth_admission"
down_revision = "platform_0063_anonymous_totals"
branch_labels = None
depends_on = None

# Self-contained historical definition; never import an older migration at runtime.
SUBJECT_GUARD = """CREATE OR REPLACE FUNCTION public.account_require_open_subjects(p_subjects text[])
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
    DECLARE candidate text; parent text; canonical text[] := ARRAY[]::text[];
    BEGIN
      IF coalesce(cardinality(p_subjects),0)>32 THEN
        RAISE EXCEPTION 'Account authority unavailable' USING ERRCODE='42501';
      END IF;
      FOREACH candidate IN ARRAY coalesce(p_subjects,ARRAY[]::text[]) LOOP
        IF candidate IS NULL THEN CONTINUE; END IF;
        IF length(btrim(candidate))=0 OR length(candidate)>512 THEN
          RAISE EXCEPTION 'Account authority unavailable' USING ERRCODE='42501';
        END IF;
        IF candidate LIKE 'apikey:%' THEN
          IF substring(candidate,8) !~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$' THEN
            RAISE EXCEPTION 'Account authority unavailable' USING ERRCODE='42501';
          END IF;
          SELECT created_by_sub INTO parent FROM public.api_keys
            WHERE id=substring(candidate,8)::uuid AND revoked_at IS NULL;
          IF parent IS NULL OR parent LIKE 'apikey:%' OR length(btrim(parent))=0 THEN
            RAISE EXCEPTION 'Account authority unavailable' USING ERRCODE='42501';
          END IF;
          canonical := array_append(canonical,parent);
        ELSE
          canonical := array_append(canonical,candidate);
        END IF;
      END LOOP;
      -- Resolve all actors before acquiring locks, ordered by actual lock ID.
      -- Opposite renter/host pairs therefore cannot acquire these in reverse.
      FOR candidate IN SELECT value FROM (SELECT DISTINCT value COLLATE "C" AS value FROM unnest(canonical) AS t(value)) AS ordered
        ORDER BY hashtextextended('identity-retirement:'||value,0), value LOOP
        PERFORM pg_advisory_xact_lock(hashtextextended('identity-retirement:'||candidate,0));
        IF EXISTS(SELECT 1 FROM public.identity_retirements WHERE subject=candidate) THEN
          RAISE EXCEPTION 'Account is unavailable' USING ERRCODE='42501';
        END IF;
      END LOOP;
    END $$"""
ISOLATION_GUARD = """IF current_setting('transaction_isolation') <> 'read committed' THEN
        RAISE EXCEPTION 'Account admission requires READ COMMITTED' USING ERRCODE='42501';
      END IF;"""


PROFILE_GUARD = r"""CREATE OR REPLACE FUNCTION public.platform_account_admission()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
    BEGIN
      IF TG_TABLE_NAME='users' THEN
        IF TG_OP='UPDATE' AND OLD.deleted_at IS NOT NULL
            AND OLD.email ~ '^closed\+[a-z2-7]{52}@account\.invalid$' THEN
          IF NEW.id IS DISTINCT FROM OLD.id OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
              OR NEW.keycloak_sub IS NOT NULL OR NEW.is_active
              OR NEW.deleted_at IS NULL OR NEW.email IS DISTINCT FROM OLD.email THEN
            RAISE EXCEPTION 'Retired profile identity cannot be reassigned' USING ERRCODE='42501';
          END IF;
        END IF;
        IF TG_OP='UPDATE' AND NEW.id=OLD.id
            AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id
            AND NEW.keycloak_sub IS NULL AND NOT NEW.is_active
            AND NEW.deleted_at IS NOT NULL
            AND NEW.email ~ '^closed\+[a-z2-7]{52}@account\.invalid$' THEN
          -- Terminal scrub is permitted, but the immutable stub check above
          -- makes this transition irreversible. Ordinary inactive unlinking
          -- must still lock and check the old subject.
          RETURN NEW;
        END IF;
        IF TG_OP='UPDATE' AND (NEW.id IS DISTINCT FROM OLD.id
            OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
            OR NEW.keycloak_sub IS DISTINCT FROM OLD.keycloak_sub) THEN
          PERFORM public.account_require_open_subjects(ARRAY[OLD.keycloak_sub,NEW.keycloak_sub]);
          RETURN NEW;
        END IF;
        IF TG_OP='UPDATE' AND NEW.keycloak_sub IS NOT DISTINCT FROM OLD.keycloak_sub
            AND NOT (NEW.is_active AND NOT OLD.is_active) THEN RETURN NEW; END IF;
        PERFORM public.account_require_open_subjects(ARRAY[NEW.keycloak_sub]);
      ELSIF TG_TABLE_NAME='api_keys' THEN
        IF TG_OP='UPDATE' AND NEW.created_by_sub IS DISTINCT FROM OLD.created_by_sub THEN
          RAISE EXCEPTION 'Credential ownership cannot be reassigned' USING ERRCODE='42501';
        END IF;
        IF TG_OP='UPDATE' AND NEW.created_by_sub IS NOT DISTINCT FROM OLD.created_by_sub
            AND NOT (OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS NULL) THEN RETURN NEW; END IF;
        PERFORM public.account_require_open_subjects(ARRAY[NEW.created_by_sub]);
      ELSE
        RAISE EXCEPTION 'Unsupported account admission context';
      END IF;
      RETURN NEW;
    END $$"""


def upgrade():
    # A snapshot taken before waiting on retirement cannot authorize a new write.
    op.execute(SUBJECT_GUARD.replace("BEGIN\n", "BEGIN\n      " + ISOLATION_GUARD + "\n", 1))
    op.execute(PROFILE_GUARD.replace(
        "OR NEW.deleted_at IS NULL OR NEW.email IS DISTINCT FROM OLD.email THEN",
        """OR NEW.deleted_at IS DISTINCT FROM OLD.deleted_at
              OR NEW.email IS DISTINCT FROM OLD.email
              OR NEW.first_name IS DISTINCT FROM '' OR NEW.last_name IS DISTINCT FROM ''
              OR NEW.gender IS DISTINCT FROM 'unspecified'
              OR NEW.image_url IS NOT NULL OR NEW.password IS NOT NULL
              OR NEW.sso_provider_id IS NOT NULL OR NEW.sociacl_attributes IS NOT NULL
              OR NEW.role_id IS NOT NULL OR NEW.activated_at IS NOT NULL THEN""",
    ))
    op.execute("""CREATE FUNCTION public.platform_auth_artifact_admission()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE subjects text[]; candidate text;
    BEGIN
      IF TG_TABLE_NAME='user_wallet_bindings' THEN
        IF TG_OP='UPDATE' AND NEW.keycloak_sub IS DISTINCT FROM OLD.keycloak_sub THEN
          RAISE EXCEPTION 'Credential ownership cannot be reassigned' USING ERRCODE='42501';
        END IF;
        subjects := ARRAY[NEW.keycloak_sub];
      ELSIF TG_TABLE_NAME IN ('user_password_resets','user_magic_links') THEN
        IF TG_OP='UPDATE' AND (NEW.user_id IS DISTINCT FROM OLD.user_id
            OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id) THEN
          RAISE EXCEPTION 'Credential ownership cannot be reassigned' USING ERRCODE='42501';
        END IF;
        -- Resolve without a row lock; retirement authority always comes first.
        subjects := public.account_subjects_for_person(NEW.user_id);
      ELSE
        RAISE EXCEPTION 'Unsupported credential admission context';
      END IF;
      -- The outer DML may already own an auth row or FK key-share lock.
      -- Never wait on retirement from a row trigger: cleanup owns retirement
      -- before touching those rows. Contention must roll back and retry.
      FOR candidate IN SELECT value FROM (
        SELECT DISTINCT value COLLATE "C" AS value FROM unnest(subjects) AS t(value)
      ) AS ordered ORDER BY hashtextextended('identity-retirement:'||value,0),value LOOP
        IF candidate IS NULL OR candidate LIKE 'apikey:%' THEN
          RAISE EXCEPTION 'Account identity required' USING ERRCODE='42501';
        END IF;
        IF NOT pg_try_advisory_xact_lock(hashtextextended('identity-retirement:'||candidate,0)) THEN
          RAISE EXCEPTION 'Account admission busy; retry' USING ERRCODE='40001';
        END IF;
      END LOOP;
      PERFORM public.account_require_open_subjects(subjects);
      IF TG_TABLE_NAME IN ('user_password_resets','user_magic_links') THEN
        -- Once the canonical identity locks are held, stabilize and recheck
        -- the actual binding. Never acquire a different subject under this row.
        PERFORM 1 FROM public.users WHERE id=NEW.user_id FOR UPDATE NOWAIT;
        IF NOT FOUND THEN
          RAISE EXCEPTION 'Account authority unavailable' USING ERRCODE='42501';
        END IF;
        IF public.account_subjects_for_person(NEW.user_id) IS DISTINCT FROM subjects THEN
          RAISE EXCEPTION 'Account binding changed; retry' USING ERRCODE='40001';
        END IF;
      END IF;
      RETURN NEW;
    EXCEPTION WHEN lock_not_available THEN
      RAISE EXCEPTION 'Account admission busy; retry' USING ERRCODE='40001';
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.platform_auth_artifact_admission() FROM PUBLIC")
    op.execute("""CREATE TRIGGER account_auth_admission AFTER INSERT OR UPDATE ON public.user_wallet_bindings
      FOR EACH ROW EXECUTE FUNCTION public.platform_auth_artifact_admission()""")
    op.execute("""CREATE TRIGGER account_auth_admission AFTER INSERT OR UPDATE ON public.user_password_resets
      FOR EACH ROW EXECUTE FUNCTION public.platform_auth_artifact_admission()""")
    op.execute("""CREATE TRIGGER account_auth_admission AFTER INSERT OR UPDATE ON public.user_magic_links
      FOR EACH ROW EXECUTE FUNCTION public.platform_auth_artifact_admission()""")


def downgrade():
    # Serialize the emptiness check with writers recording new closure evidence.
    op.execute("""LOCK TABLE public.identity_retirements, public.account_lifecycles,
        public.account_lifecycle_scopes, public.api_key_owner_closures IN SHARE MODE""")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("DROP TRIGGER account_auth_admission ON public.user_wallet_bindings")
    op.execute("DROP TRIGGER account_auth_admission ON public.user_password_resets")
    op.execute("DROP TRIGGER account_auth_admission ON public.user_magic_links")
    op.execute("DROP FUNCTION public.platform_auth_artifact_admission()")
    op.execute(SUBJECT_GUARD)
    op.execute(PROFILE_GUARD)
