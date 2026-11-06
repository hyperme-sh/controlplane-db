"""Extend transaction-only expiry permissions to person-wide payer risk."""

from alembic import op

revision = "platform_0077_payer_risk_gc"
down_revision = "platform_0076_worker_check"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""CREATE OR REPLACE FUNCTION public.account_issue_financial_transition(
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
          'payment:payer_mismatch_accounts','billing:billing_records', 'payment:host_payout_addresses', 'payment:connect_recipient_accounts',
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
        coalesce(p_before->>'id',p_before->>'lease_id',p_before->>'order_id',p_before->>'revision_id',p_before->>'host_org_id',p_before->>'account_key') END;
      IF native_resource IS DISTINCT FROM p_resource OR (p_after IS NOT NULL AND (
        p_after->>'tenant_id' IS DISTINCT FROM p_tenant::text
        OR (CASE WHEN p_kind='host_payout_addresses' THEN
          (p_after->>'host_org_id')||':'||(p_after->>'chain_id') ELSE
          coalesce(p_after->>'id',p_after->>'lease_id',p_after->>'order_id',p_after->>'revision_id',p_after->>'host_org_id',p_after->>'account_key') END)
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
    op.execute("""CREATE FUNCTION public.account_unbind_expired_payer_risk(p_before jsonb)
    RETURNS void LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$ BEGIN
      IF NOT public.account_financial_transition_allowed('payment','payer_mismatch_accounts',
        p_before->>'account_key',p_before,NULL) THEN
        RAISE EXCEPTION 'Current payer risk expiry permission required' USING ERRCODE='42501';
      END IF;
      DELETE FROM public.account_financial_source_bindings WHERE tenant_id IS NULL
        AND owner='payment' AND kind='payer_mismatch_accounts' AND resource=p_before->>'account_key';
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.account_unbind_expired_payer_risk(jsonb) FROM PUBLIC")


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("""DO $$ BEGIN
      IF to_regprocedure('public.payment_erase_expired_payer_risk(text,timestamptz,integer)') IS NOT NULL THEN
        RAISE EXCEPTION 'Remove payment payer risk expiry before its platform support';
      END IF;
    END $$""")
    op.execute("DROP FUNCTION public.account_unbind_expired_payer_risk(jsonb)")
    op.execute("""CREATE OR REPLACE FUNCTION public.account_issue_financial_transition(
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
