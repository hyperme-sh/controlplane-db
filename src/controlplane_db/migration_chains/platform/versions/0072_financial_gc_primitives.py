"""Lock every native financial party before a destructive owner transaction."""

import sqlalchemy as sa
from alembic import op

revision = "platform_0072_gc_parties"
down_revision = "platform_0071_model_wait"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""CREATE FUNCTION public.account_lock_financial_gc_parties(
      p_subject text,p_closed_at timestamptz,p_tenant uuid,p_parties text[],p_expected_epoch bigint DEFAULT NULL)
    RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE candidate text;
    BEGIN
      -- Required before any owner source-table probe, retained through commit.
      LOCK TABLE public.account_financial_fence_versions IN SHARE MODE;
      IF current_setting('transaction_isolation')<>'read committed'
        OR p_subject IS NULL OR p_parties IS NULL OR cardinality(p_parties) NOT BETWEEN 1 AND 1000
        OR NOT (p_subject=ANY(p_parties))
        OR cardinality(p_parties)<>(SELECT count(DISTINCT value) FROM unnest(p_parties) value)
        OR EXISTS(SELECT 1 FROM unnest(p_parties) value WHERE value IS NULL
          OR length(btrim(value))=0 OR length(value)>512 OR value LIKE 'apikey:%')
        OR (SELECT count(*) FROM public.account_financial_fence_versions
          WHERE owner IN ('billing','payment','hypermesh') AND protocol=1)<>3 THEN
        RAISE EXCEPTION 'Canonical native financial parties required' USING ERRCODE='42501';
      END IF;
      -- A caller may already own its lifecycle row after native discovery.
      -- All cross-party acquisitions are nonblocking: never form a row/identity
      -- cycle with ordinary source writers or row-first preservation updates.
      FOR candidate IN SELECT value FROM unnest(p_parties) value
        ORDER BY hashtextextended('identity-retirement:'||value,0),value LOOP
        IF NOT pg_try_advisory_xact_lock(hashtextextended('identity-retirement:'||candidate,0)) THEN
          RAISE EXCEPTION 'Financial party discovery must retry' USING ERRCODE='40001';
        END IF;
      END LOOP;
      FOR candidate IN SELECT value FROM unnest(p_parties) value ORDER BY value LOOP
        BEGIN
          PERFORM 1 FROM public.account_lifecycles WHERE subject=candidate FOR UPDATE NOWAIT;
        EXCEPTION WHEN lock_not_available THEN
          RAISE EXCEPTION 'Financial party lifecycle must retry' USING ERRCODE='40001';
        END;
      END LOOP;
      PERFORM public.account_lock_financial_inventory(p_subject,p_closed_at,p_tenant);
      IF EXISTS(SELECT 1 FROM public.account_lifecycles WHERE subject=ANY(p_parties)
        AND (financial_hold OR financial_deleted_at IS NOT NULL)) THEN
        RAISE EXCEPTION 'Financial party preservation prevents erasure' USING ERRCODE='42501';
      END IF;
      RETURN public.account_financial_epoch(p_subject,p_closed_at,p_tenant,p_expected_epoch);
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_lock_financial_gc_parties(text,timestamptz,uuid,text[],bigint) FROM PUBLIC")

    op.create_table(
        "account_financial_transitions",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("transaction_id", sa.String(20), nullable=False),
        sa.Column("owner", sa.String(16), nullable=False),
        sa.Column("kind", sa.String(48), nullable=False),
        sa.Column("resource", sa.String(512), nullable=False),
        sa.Column("before_digest", sa.LargeBinary(), nullable=False),
        sa.Column("after_digest", sa.LargeBinary()),
        sa.CheckConstraint("transaction_id ~ '^[0-9]{1,20}$'", name="ck_fin_transition_transaction"),
        sa.CheckConstraint("owner IN ('billing','payment','hypermesh')", name="ck_fin_transition_owner"),
        sa.CheckConstraint("kind ~ '^[a-z_]{1,48}$' AND length(resource)>0", name="ck_fin_transition_resource"),
        sa.CheckConstraint("octet_length(before_digest)=32 AND (after_digest IS NULL OR octet_length(after_digest)=32)", name="ck_fin_transition_digest"),
        sa.UniqueConstraint("transaction_id", "owner", "kind", "resource", name="uq_fin_transition_source"),
    )
    op.execute("ALTER TABLE public.account_financial_transitions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.account_financial_transitions FORCE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON TABLE public.account_financial_transitions FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.account_financial_transition_ephemeral()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$ BEGIN
      IF EXISTS(SELECT 1 FROM public.account_financial_transitions WHERE id=NEW.id) THEN
        RAISE EXCEPTION 'Financial transition capabilities cannot survive commit' USING ERRCODE='23514';
      END IF;
      RETURN NULL;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_financial_transition_ephemeral() FROM PUBLIC")
    op.execute("""CREATE CONSTRAINT TRIGGER financial_transitions_ephemeral
      AFTER INSERT ON public.account_financial_transitions DEFERRABLE INITIALLY DEFERRED
      FOR EACH ROW EXECUTE FUNCTION public.account_financial_transition_ephemeral()""")
    op.execute("""CREATE FUNCTION public.account_issue_financial_transition(
      p_subject text,p_closed_at timestamptz,p_tenant uuid,p_parties text[],
      p_owner text,p_kind text,p_resource text,p_before jsonb,p_after jsonb,
      p_expected_epoch bigint DEFAULT NULL)
    RETURNS uuid LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE capability uuid; activity_at timestamptz; retain_until timestamptz; native_resource text;
    BEGIN
      PERFORM public.account_lock_financial_gc_parties(p_subject,p_closed_at,p_tenant,p_parties,p_expected_epoch);
      PERFORM public.account_require_financial_inventory(p_subject,p_closed_at);
      IF p_owner IS NULL OR p_kind IS NULL OR (p_owner||':'||p_kind) NOT IN (
          'billing:billing_records', 'payment:host_payout_addresses', 'payment:connect_recipient_accounts',
          'payment:billing_tax_orders','payment:billing_tax_calculations','payment:connect_bank_approvals',
          'payment:connect_reversal_exposure_observations','payment:connect_control_proofs',
          'hypermesh:hypermesh_leases','hypermesh:hypermesh_payouts','hypermesh:hypermesh_orders','hypermesh:hypermesh_fills')
        OR p_resource IS NULL OR length(p_resource) NOT BETWEEN 1 AND 512
        OR jsonb_typeof(p_before) IS DISTINCT FROM 'object'
        OR (p_after IS NOT NULL AND jsonb_typeof(p_after) IS DISTINCT FROM 'object')
        OR p_before->>'tenant_id' IS DISTINCT FROM p_tenant::text
        OR p_before->>'financial_activity_at' IS NULL OR p_before->>'financial_retain_until' IS NULL THEN
        RAISE EXCEPTION 'Native aged financial transition required' USING ERRCODE='42501';
      END IF;
      native_resource:=CASE WHEN p_kind='host_payout_addresses' THEN
        (p_before->>'host_org_id')||':'||(p_before->>'chain_id') ELSE
        coalesce(p_before->>'id',p_before->>'lease_id',p_before->>'order_id',p_before->>'revision_id',p_before->>'host_org_id') END;
      IF native_resource IS DISTINCT FROM p_resource OR (p_after IS NOT NULL AND (
        p_after->>'tenant_id' IS DISTINCT FROM p_tenant::text
        OR (CASE WHEN p_kind='host_payout_addresses' THEN
          (p_after->>'host_org_id')||':'||(p_after->>'chain_id') ELSE
          coalesce(p_after->>'id',p_after->>'lease_id',p_after->>'order_id',p_after->>'revision_id',p_after->>'host_org_id') END)
          IS DISTINCT FROM p_resource)) THEN
        RAISE EXCEPTION 'Native financial source identity required' USING ERRCODE='42501';
      END IF;
      BEGIN
        activity_at:=(p_before->>'financial_activity_at')::timestamptz;
        retain_until:=(p_before->>'financial_retain_until')::timestamptz;
      EXCEPTION WHEN data_exception THEN
        RAISE EXCEPTION 'Native financial clock required' USING ERRCODE='42501';
      END;
      IF NOT isfinite(activity_at) OR NOT isfinite(retain_until)
        OR retain_until>transaction_timestamp() OR retain_until IS DISTINCT FROM
          ((activity_at AT TIME ZONE 'UTC')+interval '7 years') AT TIME ZONE 'UTC'
        OR (p_after IS NOT NULL AND (
          p_after->'financial_activity_at' IS DISTINCT FROM p_before->'financial_activity_at'
          OR p_after->'financial_retain_until' IS DISTINCT FROM p_before->'financial_retain_until')) THEN
        RAISE EXCEPTION 'Recorded seven-year financial retention must expire' USING ERRCODE='42501';
      END IF;
      -- This private primitive is not a source erasure entry point. Native
      -- owner commands separately prove current legal ownership and finality,
      -- under source row locks, before issuing these exact image capabilities.
      INSERT INTO public.account_financial_transitions
        (transaction_id,owner,kind,resource,before_digest,after_digest)
      VALUES(pg_current_xact_id()::text,p_owner,p_kind,p_resource,
        sha256(convert_to(p_before::text,'UTF8')),
        CASE WHEN p_after IS NULL THEN NULL ELSE sha256(convert_to(p_after::text,'UTF8')) END)
      RETURNING id INTO capability;
      RETURN capability;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_issue_financial_transition(text,timestamptz,uuid,text[],text,text,text,jsonb,jsonb,bigint) FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.account_financial_transition_allowed(
      p_owner text,p_kind text,p_resource text,p_before jsonb,p_after jsonb)
    RETURNS boolean LANGUAGE sql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
      SELECT EXISTS(SELECT 1 FROM public.account_financial_transitions
        WHERE transaction_id=pg_current_xact_id()::text AND owner=p_owner AND kind=p_kind AND resource=p_resource
          AND before_digest=sha256(convert_to(p_before::text,'UTF8'))
          AND after_digest IS NOT DISTINCT FROM
            CASE WHEN p_after IS NULL THEN NULL ELSE sha256(convert_to(p_after::text,'UTF8')) END)
    $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_financial_transition_allowed(text,text,text,jsonb,jsonb) FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.account_finish_financial_transition(p_capability uuid)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$ BEGIN
      DELETE FROM public.account_financial_transitions WHERE id=p_capability
        AND transaction_id=pg_current_xact_id()::text;
      IF NOT FOUND THEN RAISE EXCEPTION 'Current financial transition required' USING ERRCODE='42501'; END IF;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_finish_financial_transition(uuid) FROM PUBLIC")

    op.execute("""CREATE FUNCTION public.account_merge_anonymous_total(
      p_metric text,p_currency text,p_unit text,p_amount numeric)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$ BEGIN
      IF p_metric IS NULL OR p_metric NOT IN (
          'invoice_paid','charge_captured','refund_paid','processor_cost','tax_collected','tax_refunded',
          'host_gross','host_net','platform_take','host_usdc','lease_delivered','pricing_fill','pricing_tip')
        OR p_currency IS NULL OR p_unit IS NULL
        OR NOT ((p_currency ~ '^[A-Z]{3}$' AND p_unit='minor')
          OR (p_currency='USDC' AND p_unit IN ('usdc_atom','usdc_cent')))
        OR p_amount IS NULL OR p_amount<>trunc(p_amount) OR abs(p_amount)>=1e78::numeric THEN
        RAISE EXCEPTION 'Exact anonymous accounting dimensions and amount required' USING ERRCODE='42501';
      END IF;
      IF p_amount=0 THEN RETURN; END IF;
      INSERT INTO public.financial_accounting_totals(metric,currency,unit,amount)
      VALUES(p_metric,p_currency,p_unit,p_amount)
      ON CONFLICT(metric,currency,unit) DO UPDATE
        SET amount=public.financial_accounting_totals.amount+EXCLUDED.amount;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_merge_anonymous_total(text,text,text,numeric) FROM PUBLIC")


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("DROP FUNCTION public.account_merge_anonymous_total(text,text,text,numeric)")
    op.execute("DROP FUNCTION public.account_finish_financial_transition(uuid)")
    op.execute("DROP FUNCTION public.account_financial_transition_allowed(text,text,text,jsonb,jsonb)")
    op.execute("DROP FUNCTION public.account_issue_financial_transition(text,timestamptz,uuid,text[],text,text,text,jsonb,jsonb,bigint)")
    op.drop_table("account_financial_transitions")
    op.execute("DROP FUNCTION public.account_financial_transition_ephemeral()")
    op.execute("DROP FUNCTION public.account_lock_financial_gc_parties(text,timestamptz,uuid,text[],bigint)")
