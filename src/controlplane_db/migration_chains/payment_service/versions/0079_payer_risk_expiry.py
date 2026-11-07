"""Expire unreserved personal payer-risk state after native seven-year retention."""

import sqlalchemy as sa
from alembic import op

revision = "payment_service_0079_risk_gc"
down_revision = "payment_service_0078_privacy"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""DO $$ BEGIN
      IF to_regprocedure('public.account_unbind_expired_payer_risk(jsonb)') IS NULL THEN
        RAISE EXCEPTION 'Platform payer risk expiry support required';
      END IF;
    END $$""")
    for column in ('financial_activity_at', 'financial_retain_until'):
        op.add_column('payer_mismatch_accounts', sa.Column(column, sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint('ck_payer_mismatch_accounts_financial_clock', 'payer_mismatch_accounts',
        '(financial_activity_at IS NULL AND financial_retain_until IS NULL) OR '
        '(financial_activity_at IS NOT NULL AND financial_retain_until IS NOT NULL AND financial_retain_until > financial_activity_at)')
    op.create_index('ix_payer_mismatch_accounts_financial_due', 'payer_mismatch_accounts', ['financial_retain_until'])
    # Historical native observations are the only backfill authority. A row with
    # no recorded activity remains unknown; migration time is never its age.
    op.execute("ALTER TABLE public.payer_mismatch_accounts NO FORCE ROW LEVEL SECURITY")
    op.execute("""UPDATE public.payer_mismatch_accounts SET
      financial_activity_at=greatest(last_mismatch_at,last_checkout_at,day::timestamp AT TIME ZONE 'UTC'),
      financial_retain_until=((greatest(last_mismatch_at,last_checkout_at,day::timestamp AT TIME ZONE 'UTC')
        AT TIME ZONE 'UTC')+interval '7 years') AT TIME ZONE 'UTC'
      WHERE (last_mismatch_at IS NOT NULL OR last_checkout_at IS NOT NULL)
        AND (last_mismatch_at IS NULL OR isfinite(last_mismatch_at))
        AND (last_checkout_at IS NULL OR isfinite(last_checkout_at)) AND isfinite(day)""")
    op.execute("ALTER TABLE public.payer_mismatch_accounts FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE TRIGGER account_financial_clock BEFORE INSERT OR UPDATE ON public.payer_mismatch_accounts
      FOR EACH ROW EXECUTE FUNCTION public.payment_financial_clock()""")
    op.execute("""CREATE FUNCTION public.payment_payer_risk_expiry_guard()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$ BEGIN
      IF NOT public.account_financial_transition_allowed('payment','payer_mismatch_accounts',
        OLD.account_key,to_jsonb(OLD),NULL) THEN
        RAISE EXCEPTION 'Payer risk requires recorded expiry' USING ERRCODE='42501';
      END IF;
      RETURN OLD;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.payment_payer_risk_expiry_guard() FROM PUBLIC")
    op.execute("""CREATE TRIGGER account_payer_risk_expiry BEFORE DELETE ON public.payer_mismatch_accounts
      FOR EACH ROW EXECUTE FUNCTION public.payment_payer_risk_expiry_guard()""")
    op.execute("""CREATE FUNCTION public.payment_erase_expired_payer_risk(
      p_subject text,p_closed_at timestamptz,p_limit integer DEFAULT 100)
    RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE source_record jsonb; parties text[]; verified_parties text[]; capability uuid;
      source_key text; processed integer:=0; remaining bigint; next_due timestamptz;
    BEGIN
      IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 1000 THEN
        RAISE EXCEPTION 'Bounded payer risk expiry required' USING ERRCODE='42501';
      END IF;
      -- The key is an exact native person hash, never a company initiator or a
      -- contact match. Include every retained association when checking holds.
      source_key:=encode(sha256(convert_to(p_subject,'UTF8')),'hex');
      SELECT array_agg(p.subject ORDER BY p.subject) INTO parties FROM public.account_financial_parties(
        NULL,NULL,NULL,'payment','payer_mismatch_accounts',source_key,source_key) p;
      PERFORM public.account_lock_financial_gc_parties(p_subject,p_closed_at,NULL,parties,NULL);
      PERFORM public.account_require_personal_erasure(p_subject,NULL);
      PERFORM public.account_require_financial_inventory(p_subject,p_closed_at);
      SELECT to_jsonb(r) INTO source_record FROM public.payer_mismatch_accounts r
        WHERE account_key=source_key FOR UPDATE NOWAIT;
      IF FOUND THEN
        SELECT array_agg(p.subject ORDER BY p.subject) INTO verified_parties FROM public.account_financial_parties(
          NULL,NULL,NULL,'payment','payer_mismatch_accounts',source_key,source_key) p;
        IF verified_parties IS DISTINCT FROM parties THEN
          RAISE EXCEPTION 'Payer risk associations changed; retry' USING ERRCODE='40001';
        END IF;
        IF (source_record->>'reserved_count')::integer=0 AND (source_record->>'reserved_cents')::bigint=0
          AND (source_record->>'financial_retain_until')::timestamptz<=transaction_timestamp() THEN
          capability:=public.account_issue_financial_transition(p_subject,p_closed_at,NULL,parties,
            'payment','payer_mismatch_accounts',source_key,source_record,NULL,NULL);
          DELETE FROM public.payer_mismatch_accounts WHERE account_key=source_key;
          PERFORM public.account_unbind_expired_payer_risk(source_record);
          PERFORM public.account_finish_financial_transition(capability);
          processed:=1;
        END IF;
      END IF;
      SELECT count(*),min(financial_retain_until) FILTER(WHERE financial_retain_until>transaction_timestamp())
        INTO remaining,next_due FROM public.payer_mismatch_accounts WHERE account_key=source_key;
      -- Risk counters are not money balances. No source identifiers, hashes,
      -- timestamps or person dimensions enter anonymous accounting totals.
      RETURN jsonb_build_object('complete',remaining=0,'processed',processed,'remaining',remaining,'next_due_at',next_due);
    EXCEPTION WHEN lock_not_available THEN
      RAISE EXCEPTION 'Payer risk expiry must retry' USING ERRCODE='40001';
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.payment_erase_expired_payer_risk(text,timestamptz,integer) FROM PUBLIC")


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("DROP FUNCTION public.payment_erase_expired_payer_risk(text,timestamptz,integer)")
    op.execute("DROP TRIGGER account_payer_risk_expiry ON public.payer_mismatch_accounts")
    op.execute("DROP FUNCTION public.payment_payer_risk_expiry_guard()")
    op.execute("DROP TRIGGER account_financial_clock ON public.payer_mismatch_accounts")
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM public.payer_mismatch_accounts
      WHERE financial_activity_at IS NOT NULL OR financial_retain_until IS NOT NULL) THEN
      RAISE EXCEPTION 'Recorded payer risk clocks cannot be discarded'; END IF; END $$""")
    op.drop_index('ix_payer_mismatch_accounts_financial_due', table_name='payer_mismatch_accounts')
    op.drop_constraint('ck_payer_mismatch_accounts_financial_clock', 'payer_mismatch_accounts', type_='check')
    op.drop_column('payer_mismatch_accounts', 'financial_retain_until')
    op.drop_column('payer_mismatch_accounts', 'financial_activity_at')
