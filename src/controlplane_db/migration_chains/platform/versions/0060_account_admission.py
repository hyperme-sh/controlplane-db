"""Serialize credential and identity admission with durable realm retirement."""

from alembic import op

revision = "platform_0060_account_admission"
down_revision = "platform_0059_account_lifecycles"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE FUNCTION public.account_assert_guards_removable()
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog
    SET row_security=off AS $$ BEGIN
      IF EXISTS(SELECT 1 FROM public.identity_retirements)
        OR EXISTS(SELECT 1 FROM public.account_lifecycles)
        OR EXISTS(SELECT 1 FROM public.account_lifecycle_scopes)
        OR EXISTS(SELECT 1 FROM public.api_key_owner_closures) THEN
        RAISE EXCEPTION 'Recorded account admission fences cannot be discarded';
      END IF;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_assert_guards_removable() FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.account_require_open_subjects(p_subjects text[])
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
    END $$""")
    op.execute("""CREATE FUNCTION public.account_subjects_for_person(p_person uuid)
    RETURNS text[] LANGUAGE plpgsql STABLE SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE identity_sub text; inactive boolean;
    BEGIN
      IF p_person IS NULL THEN RETURN ARRAY[]::text[]; END IF;
      -- IDs are globally unique. Never match an email, or assume a directory
      -- primary key is also its issuer subject. Ownership loss must error,
      -- rather than allowing RLS to silently hide a retired canonical person.
      SELECT keycloak_sub, (NOT is_active OR deleted_at IS NOT NULL)
        INTO identity_sub,inactive FROM public.users WHERE id=p_person;
      IF inactive IS TRUE THEN
        RAISE EXCEPTION 'Account is unavailable' USING ERRCODE='42501';
      END IF;
      RETURN array_remove(ARRAY[p_person::text,identity_sub],NULL);
    END $$""")
    op.execute("""CREATE FUNCTION public.platform_account_admission()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
    BEGIN
      IF TG_TABLE_NAME='users' THEN
        IF TG_OP='UPDATE' AND OLD.deleted_at IS NOT NULL
            AND OLD.email ~ '^closed\\+[a-z2-7]{52}@account\\.invalid$' THEN
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
            AND NEW.email ~ '^closed\\+[a-z2-7]{52}@account\\.invalid$' THEN
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
    END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.account_require_open_subjects(text[]) FROM PUBLIC"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION public.account_subjects_for_person(uuid) FROM PUBLIC"
    )
    op.execute("REVOKE ALL ON FUNCTION public.platform_account_admission() FROM PUBLIC")
    # AFTER triggers distinguish actual INSERTs from ON CONFLICT maintenance
    # updates. A BEFORE INSERT guard would also block harmless existing rows.
    op.execute("""CREATE TRIGGER account_user_admission AFTER INSERT OR UPDATE ON public.users
        FOR EACH ROW EXECUTE FUNCTION public.platform_account_admission()""")
    op.execute("""CREATE TRIGGER account_key_admission AFTER INSERT OR UPDATE ON public.api_keys
        FOR EACH ROW EXECUTE FUNCTION public.platform_account_admission()""")


def downgrade():
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("DROP TRIGGER account_key_admission ON public.api_keys")
    op.execute("DROP TRIGGER account_user_admission ON public.users")
    op.execute("DROP FUNCTION public.platform_account_admission()")
    op.execute("DROP FUNCTION public.account_subjects_for_person(uuid)")
    op.execute("DROP FUNCTION public.account_require_open_subjects(text[])")
    op.execute("DROP FUNCTION public.account_assert_guards_removable()")
