"""Invalidate financial owner proofs when native source facts change."""

import sqlalchemy as sa
from alembic import op

revision = "platform_0065_financial_epochs"
down_revision = "platform_0064_auth_admission"
branch_labels = None
depends_on = None


def upgrade():
    # Only owner migrations register a complete native write fence. A partial
    # installation must never authorize a cross-owner cleanup proof.
    op.create_table("account_financial_fence_versions",
        sa.Column("owner", sa.String(16), primary_key=True),
        sa.Column("protocol", sa.Integer(), nullable=False),
        sa.CheckConstraint("owner IN ('billing','payment','hypermesh')", name="ck_financial_fence_owner"),
        sa.CheckConstraint("protocol > 0", name="ck_financial_fence_protocol"))
    op.execute("INSERT INTO public.account_financial_fence_versions(owner,protocol) VALUES ('billing',1)")
    op.create_table("account_financial_source_bindings",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("subject", sa.String(512), sa.ForeignKey("account_lifecycles.subject", ondelete="RESTRICT"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), sa.ForeignKey("tenants.id", ondelete="RESTRICT")),
        sa.Column("owner", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(48), nullable=False),
        sa.Column("resource", sa.String(512), nullable=False),
        sa.CheckConstraint("owner IN ('billing','payment','hypermesh')", name="ck_financial_binding_owner"),
        sa.CheckConstraint("kind ~ '^[a-z_]{1,48}$' AND length(resource)>0", name="ck_financial_binding_resource"))
    op.create_unique_constraint("uq_account_financial_source", "account_financial_source_bindings",
        ["subject","tenant_id","owner","kind","resource"], postgresql_nulls_not_distinct=True)
    op.create_index("ix_financial_source_lookup", "account_financial_source_bindings", ["tenant_id","owner","kind","resource"])
    op.execute("ALTER TABLE public.account_financial_source_bindings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.account_financial_source_bindings FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY financial_source_scope ON public.account_financial_source_bindings
      USING (tenant_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_tenant_id',true),'')::uuid)
      WITH CHECK (tenant_id IS NOT DISTINCT FROM NULLIF(current_setting('app.current_tenant_id',true),'')::uuid)""")
    op.add_column("account_lifecycles", sa.Column("financial_epoch", sa.BigInteger(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_account_financial_epoch", "account_lifecycles", "financial_epoch >= 0")
    op.execute("CREATE INDEX ix_closure_scope_financial_users ON public.account_lifecycle_scopes USING gin(user_ids)")
    op.execute("CREATE INDEX ix_closure_scope_financial_keys ON public.account_lifecycle_scopes USING gin((effects->'api_keys'->'keys'))")
    op.execute("CREATE INDEX ix_closure_platform_financial_users ON public.account_lifecycles USING gin((effects->'platform_profile'->'user_ids'))")
    op.execute("""CREATE FUNCTION public.account_touch_financial_subjects(p_subjects text[],p_recapture_subjects text[] DEFAULT NULL)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE candidate text;
    BEGIN
      IF current_setting('transaction_isolation') <> 'read committed'
        OR coalesce(cardinality(p_subjects),0)>1000
        OR coalesce(cardinality(p_recapture_subjects),0)>1000
        OR NOT (coalesce(p_recapture_subjects,ARRAY[]::text[]) <@ coalesce(p_subjects,ARRAY[]::text[])) THEN
        RAISE EXCEPTION 'Financial source authority unavailable' USING ERRCODE='42501';
      END IF;
      FOR candidate IN SELECT DISTINCT value FROM unnest(coalesce(p_subjects,ARRAY[]::text[])) value
        WHERE value IS NOT NULL ORDER BY value LOOP
        IF length(btrim(candidate))=0 OR length(candidate)>512 OR candidate LIKE 'apikey:%' THEN
          RAISE EXCEPTION 'Canonical financial source identity required' USING ERRCODE='42501';
        END IF;
      END LOOP;
      -- An outer source write can already own its row. Never wait on an
      -- identity lock while holding it: retry the complete transaction instead.
      -- Shared writer locks allow ordinary parallel financial activity;
      -- retirement, holds and erasure acquire the incompatible exclusive lock.
      FOR candidate IN SELECT value FROM (SELECT DISTINCT value FROM unnest(coalesce(p_subjects,ARRAY[]::text[])) value WHERE value IS NOT NULL) candidates
        ORDER BY hashtextextended('identity-retirement:'||value,0),value LOOP
        IF NOT pg_try_advisory_xact_lock_shared(hashtextextended('identity-retirement:'||candidate,0)) THEN
          RAISE EXCEPTION 'Financial source transaction must retry' USING ERRCODE='40001';
        END IF;
      END LOOP;
      -- Fresh READ COMMITTED visibility after locking also catches a retirement
      -- which committed after the source write began. Holds allow genuine late
      -- financial activity; they never waive native finality or retention.
      FOR candidate IN SELECT DISTINCT value FROM unnest(coalesce(p_subjects,ARRAY[]::text[])) value
        WHERE value IS NOT NULL ORDER BY value LOOP
        BEGIN
          PERFORM 1 FROM public.account_lifecycles WHERE subject=candidate FOR UPDATE NOWAIT;
        EXCEPTION WHEN lock_not_available THEN
          RAISE EXCEPTION 'Financial lifecycle transaction must retry' USING ERRCODE='40001';
        END;
        IF EXISTS(SELECT 1 FROM public.account_lifecycles
          WHERE subject=candidate AND financial_deleted_at IS NOT NULL)
          AND candidate=ANY(coalesce(p_recapture_subjects,p_subjects)) THEN
          RAISE EXCEPTION 'Completed financial identity cannot be recaptured' USING ERRCODE='42501';
        END IF;
        UPDATE public.account_lifecycles SET financial_epoch=financial_epoch+1
          WHERE subject=candidate AND financial_deleted_at IS NULL;
      END LOOP;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_touch_financial_subjects(text[],text[]) FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.account_financial_epoch(
      p_subject text,p_closed_at timestamptz,p_tenant_id uuid DEFAULT NULL,p_expected bigint DEFAULT NULL,
      p_owners text[] DEFAULT ARRAY['billing','payment','hypermesh']::text[])
    RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE current_epoch bigint;
    BEGIN
      -- Keep producer coverage installed through the caller's complete source
      -- deletion transaction; migration changes take the exclusive lock first.
      LOCK TABLE public.account_financial_fence_versions IN SHARE MODE;
      IF p_owners IS NULL OR cardinality(p_owners)=0 OR cardinality(p_owners)>3
        OR cardinality(p_owners)<>(SELECT count(DISTINCT item) FROM unnest(p_owners) item)
        OR EXISTS(SELECT 1 FROM unnest(p_owners) item WHERE item IS NULL
          OR item NOT IN ('billing','payment','hypermesh'))
        OR EXISTS(SELECT 1 FROM unnest(p_owners) item WHERE NOT EXISTS(
          SELECT 1 FROM public.account_financial_fence_versions f WHERE f.owner=item AND f.protocol=1)) THEN
        RAISE EXCEPTION 'Native financial owner fences are incomplete' USING ERRCODE='42501';
      END IF;
      PERFORM public.account_lock_financial_erasure(p_subject,p_closed_at,p_tenant_id);
      SELECT financial_epoch INTO STRICT current_epoch FROM public.account_lifecycles WHERE subject=p_subject;
      IF p_expected IS NOT NULL AND (p_expected<0 OR p_expected<>current_epoch) THEN
        RAISE EXCEPTION 'Financial owner proof changed; retry discovery' USING ERRCODE='40001';
      END IF;
      RETURN current_epoch;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_financial_epoch(text,timestamptz,uuid,bigint,text[]) FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.account_lock_financial_fence_changes()
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog SET row_security=off AS $$ BEGIN
      LOCK TABLE public.account_financial_fence_versions IN ACCESS EXCLUSIVE MODE;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_lock_financial_fence_changes() FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.account_register_financial_fence(p_owner text,p_protocol integer)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog SET row_security=off AS $$ BEGIN
      IF p_owner NOT IN ('payment','hypermesh') OR p_owner IS NULL
        OR p_protocol IS NULL OR p_protocol NOT BETWEEN 1 AND 32767 THEN
        RAISE EXCEPTION 'Native financial owner protocol required' USING ERRCODE='42501';
      END IF;
      PERFORM public.account_lock_financial_fence_changes();
      INSERT INTO public.account_financial_fence_versions(owner,protocol) VALUES(p_owner,p_protocol)
        ON CONFLICT(owner) DO UPDATE SET protocol=excluded.protocol;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_register_financial_fence(text,integer) FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.account_unregister_financial_fence(p_owner text)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$ BEGIN
      IF p_owner NOT IN ('payment','hypermesh') OR p_owner IS NULL THEN
        RAISE EXCEPTION 'Native financial owner required' USING ERRCODE='42501';
      END IF;
      PERFORM public.account_lock_financial_fence_changes();
      LOCK TABLE public.account_lifecycles IN SHARE MODE;
      PERFORM public.account_assert_guards_removable();
      DELETE FROM public.account_financial_fence_versions WHERE owner=p_owner;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_unregister_financial_fence(text) FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.account_bind_financial_source(
      p_subjects text[],p_tenant uuid,p_owner text,p_kind text,p_resource text)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE candidate text; inserted_count integer;
    BEGIN
      IF p_owner IS NULL OR p_owner NOT IN ('billing','payment','hypermesh')
        OR p_kind IS NULL OR p_kind !~ '^[a-z_]{1,48}$'
        OR p_resource IS NULL OR length(p_resource) NOT BETWEEN 1 AND 512
        OR coalesce(cardinality(p_subjects),0)>1000
        OR current_setting('transaction_isolation')<>'read committed' THEN
        RAISE EXCEPTION 'Native financial source binding required' USING ERRCODE='42501';
      END IF;
      FOR candidate IN SELECT value FROM (SELECT DISTINCT value FROM unnest(coalesce(p_subjects,ARRAY[]::text[])) value WHERE value IS NOT NULL) candidates
        ORDER BY hashtextextended('identity-retirement:'||value,0),value LOOP
        IF length(btrim(candidate))=0 OR length(candidate)>512 OR candidate LIKE 'apikey:%' THEN
          RAISE EXCEPTION 'Canonical financial identity required' USING ERRCODE='42501';
        END IF;
        IF NOT pg_try_advisory_xact_lock_shared(hashtextextended('identity-retirement:'||candidate,0)) THEN
          RAISE EXCEPTION 'Financial source binding must retry' USING ERRCODE='40001';
        END IF;
      END LOOP;
      FOR candidate IN SELECT DISTINCT value FROM unnest(coalesce(p_subjects,ARRAY[]::text[])) value
        WHERE value IS NOT NULL ORDER BY value LOOP
        BEGIN
          PERFORM 1 FROM public.account_lifecycles WHERE subject=candidate FOR UPDATE NOWAIT;
        EXCEPTION WHEN lock_not_available THEN
          RAISE EXCEPTION 'Financial lifecycle binding must retry' USING ERRCODE='40001';
        END;
        INSERT INTO public.account_financial_source_bindings(subject,tenant_id,owner,kind,resource)
          SELECT candidate,p_tenant,p_owner,p_kind,p_resource FROM public.account_lifecycles a
          WHERE a.subject=candidate AND a.financial_deleted_at IS NULL
          ON CONFLICT ON CONSTRAINT uq_account_financial_source DO NOTHING;
        GET DIAGNOSTICS inserted_count = ROW_COUNT;
        IF inserted_count>0 THEN
          UPDATE public.account_lifecycles SET financial_epoch=financial_epoch+1 WHERE subject=candidate;
        END IF;
      END LOOP;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_bind_financial_source(text[],uuid,text,text,text) FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.account_financial_parties(
      p_person uuid,p_actor text,p_tenant uuid,p_owner text DEFAULT NULL,p_kind text DEFAULT NULL,p_resource text DEFAULT NULL,p_actor_hash text DEFAULT NULL)
    RETURNS TABLE(subject text,direct_reference boolean) LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE native_actor text; native_person text; native_key uuid;
    BEGIN
      IF p_owner IS NOT NULL AND (p_owner NOT IN ('billing','payment','hypermesh')
        OR p_kind IS NULL OR p_kind !~ '^[a-z_]{1,48}$'
        OR p_resource IS NULL OR length(p_resource) NOT BETWEEN 1 AND 512) THEN
        RAISE EXCEPTION 'Native financial source reference required' USING ERRCODE='42501';
      END IF;
      IF p_actor LIKE 'apikey:%' THEN
        IF substring(p_actor,8) ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$' THEN
          native_key := substring(p_actor,8)::uuid;
          SELECT k.created_by_sub INTO native_actor FROM public.api_keys k WHERE k.id=native_key;
        END IF;
      ELSE native_actor := p_actor;
      END IF;
      SELECT u.keycloak_sub INTO native_person FROM public.users u WHERE u.id=p_person;
      RETURN QUERY SELECT c.candidate,bool_or(c.is_direct) FROM (
        SELECT unnest(ARRAY[native_actor,native_person]) AS candidate,true AS is_direct
        UNION ALL
        SELECT a.subject,true FROM public.account_lifecycles a WHERE
          p_person IS NOT NULL AND (a.effects->'platform_profile'->'user_ids') @> jsonb_build_array(p_person::text)
        UNION ALL
        SELECT sc.subject,true FROM public.account_lifecycle_scopes sc WHERE
          (p_person IS NOT NULL AND sc.user_ids @> jsonb_build_array(p_person::text))
          OR (native_key IS NOT NULL AND (sc.effects->'api_keys'->'keys') @> jsonb_build_array(jsonb_build_object('id',native_key::text)))
        UNION ALL
        SELECT a.subject,true FROM public.account_lifecycles a WHERE
          p_actor_hash ~ '^[0-9a-f]{64}$'
          AND encode(sha256(convert_to(a.subject,'UTF8')),'hex')=p_actor_hash
        UNION ALL
        SELECT b.subject,false FROM public.account_financial_source_bindings b WHERE
          b.tenant_id IS NOT DISTINCT FROM p_tenant AND b.owner=p_owner AND b.kind=p_kind AND b.resource=p_resource
      ) c WHERE c.candidate IS NOT NULL AND length(btrim(c.candidate))>0
          AND length(c.candidate)<=512 AND c.candidate NOT LIKE 'apikey:%'
        GROUP BY c.candidate;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_financial_parties(uuid,text,uuid,text,text,text,text) FROM PUBLIC")
    # A narrow platform-owned projection for native payment-owner triggers.
    # This is private transaction-local SQL, not a public cross-owner table grant.
    op.execute("""CREATE FUNCTION public.account_billing_financial_source(p_id uuid,p_tenant uuid)
    RETURNS jsonb LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
      SELECT jsonb_build_object('id',b.id,'tenant_id',b.tenant_id,'user_id',b.user_id,
        'scope',b.scope,'actor',b.actor,'status',b.status,'currency',b.currency,
        'amount',b.amount,'metadata',b.metadata,'created_at',b.created_at,
        'updated_at',b.updated_at,'financial_activity_at',b.financial_activity_at,
        'financial_retain_until',b.financial_retain_until)
      FROM public.billing_records b WHERE b.id=p_id AND b.tenant_id IS NOT DISTINCT FROM p_tenant
    $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_billing_financial_source(uuid,uuid) FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.account_refuse_financial_truncate()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$ BEGIN
      RAISE EXCEPTION 'Financial sources require recorded row erasure' USING ERRCODE='42501';
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_refuse_financial_truncate() FROM PUBLIC")
    op.execute("CREATE TRIGGER billing_financial_not_truncated BEFORE TRUNCATE ON public.billing_records FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()")
    op.execute("CREATE TRIGGER financial_bindings_not_truncated BEFORE TRUNCATE ON public.account_financial_source_bindings FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()")
    op.execute("""CREATE FUNCTION public.account_billing_financial_epoch()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE source_record jsonb; canonical text[] := ARRAY[]::text[]; captures text[] := ARRAY[]::text[];
      source_subjects text[]; direct_subjects text[];
    BEGIN
      IF TG_OP='UPDATE' AND
        (to_jsonb(NEW)-ARRAY['updated_at','financial_activity_at','financial_retain_until','metadata'])
          IS NOT DISTINCT FROM
        (to_jsonb(OLD)-ARRAY['updated_at','financial_activity_at','financial_retain_until','metadata'])
        AND public.account_billing_financial_metadata(NEW.metadata)
          IS NOT DISTINCT FROM public.account_billing_financial_metadata(OLD.metadata) THEN
        RETURN NEW;
      END IF;
      FOR source_record IN SELECT item FROM unnest(CASE WHEN TG_OP='INSERT' THEN ARRAY[to_jsonb(NEW)]
        WHEN TG_OP='DELETE' THEN ARRAY[to_jsonb(OLD)] ELSE ARRAY[to_jsonb(OLD),to_jsonb(NEW)] END) item LOOP
        SELECT array_agg(p.subject),array_agg(p.subject) FILTER(WHERE p.direct_reference)
          INTO source_subjects,direct_subjects FROM public.account_financial_parties(
            (source_record->>'user_id')::uuid,source_record->'metadata'->>'actor_sub',
            (source_record->>'tenant_id')::uuid,'billing','payment',source_record->>'id') p;
        canonical := canonical || coalesce(source_subjects,ARRAY[]::text[]);
        IF TG_OP<>'DELETE' AND source_record=to_jsonb(NEW) THEN
          captures := captures || coalesce(direct_subjects,ARRAY[]::text[]);
        END IF;
      END LOOP;
      SELECT coalesce(array_agg(DISTINCT item),ARRAY[]::text[]) INTO captures FROM unnest(captures) item WHERE item IS NOT NULL;
      SELECT array_agg(DISTINCT item) INTO canonical FROM unnest(canonical) item WHERE item IS NOT NULL;
      PERFORM public.account_touch_financial_subjects(canonical,captures);
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      PERFORM public.account_bind_financial_source(canonical,NEW.tenant_id,'billing','payment',NEW.id::text);
      RETURN NEW;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_billing_financial_epoch() FROM PUBLIC")
    op.execute("""CREATE TRIGGER billing_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.billing_records
      FOR EACH ROW EXECUTE FUNCTION public.account_billing_financial_epoch()""")


def downgrade():
    op.execute("LOCK TABLE public.account_financial_fence_versions IN ACCESS EXCLUSIVE MODE")
    op.execute("LOCK TABLE public.account_lifecycles IN SHARE MODE")
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM public.account_financial_fence_versions WHERE owner<>'billing') THEN
        RAISE EXCEPTION 'Remove dependent native owner fences before the platform fence';
      END IF;
    END $$""")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("DROP TRIGGER billing_financial_not_truncated ON public.billing_records")
    op.execute("DROP TRIGGER financial_bindings_not_truncated ON public.account_financial_source_bindings")
    op.execute("DROP FUNCTION public.account_refuse_financial_truncate()")
    op.execute("DROP TRIGGER billing_financial_epoch ON public.billing_records")
    op.execute("DROP FUNCTION public.account_billing_financial_epoch()")
    op.execute("DROP FUNCTION public.account_billing_financial_source(uuid,uuid)")
    op.execute("DROP FUNCTION public.account_unregister_financial_fence(text)")
    op.execute("DROP FUNCTION public.account_register_financial_fence(text,integer)")
    op.execute("DROP FUNCTION public.account_lock_financial_fence_changes()")
    op.execute("DROP FUNCTION public.account_bind_financial_source(text[],uuid,text,text,text)")
    op.execute("DROP FUNCTION public.account_financial_parties(uuid,text,uuid,text,text,text,text)")
    op.execute("DROP FUNCTION public.account_financial_epoch(text,timestamptz,uuid,bigint,text[])")
    op.execute("DROP FUNCTION public.account_touch_financial_subjects(text[],text[])")
    op.execute("DROP INDEX public.ix_closure_platform_financial_users")
    op.execute("DROP INDEX public.ix_closure_scope_financial_keys")
    op.execute("DROP INDEX public.ix_closure_scope_financial_users")
    op.drop_constraint("ck_account_financial_epoch", "account_lifecycles", type_="check")
    op.drop_column("account_lifecycles", "financial_epoch")
    op.drop_table("account_financial_source_bindings")
    op.drop_table("account_financial_fence_versions")
