"""Supply a fresh native payment financial retention proof."""

from alembic import op

revision = "payment_service_0080_fin_state"
down_revision = "payment_service_0079_risk_gc"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""DO $$ BEGIN
      IF to_regprocedure('public.account_native_financial_state(text,timestamptz,text)') IS NULL THEN
        RAISE EXCEPTION 'Platform financial state support required';
      END IF;
    END $$""")
    op.execute("""CREATE FUNCTION public.payment_account_financial_state(p_subject text,p_closed_at timestamptz)
    RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE source_table text; proof jsonb;
    BEGIN
      proof:=public.account_native_financial_state(p_subject,p_closed_at,'payment');
      FOREACH source_table IN ARRAY ARRAY['host_payout_addresses','connect_recipient_accounts','billing_tax_orders','billing_tax_calculations','connect_bank_approvals','connect_reversal_exposure_observations','connect_control_proofs','connect_access_states','connect_access_grants','connect_access_results','payer_mismatch_accounts'] LOOP
        IF NOT EXISTS(SELECT 1 FROM pg_catalog.pg_trigger
          WHERE tgrelid=to_regclass('public.'||source_table) AND tgname='account_financial_epoch'
            AND tgfoid=to_regprocedure('public.payment_account_financial_epoch()')
            AND tgtype=29 AND tgenabled IN ('O','A') AND NOT tgisinternal)
          OR NOT EXISTS(SELECT 1 FROM pg_catalog.pg_trigger
            WHERE tgrelid=to_regclass('public.'||source_table) AND tgname='account_financial_not_truncated'
              AND tgfoid=to_regprocedure('public.account_refuse_financial_truncate()')
              AND tgtype=34 AND tgenabled IN ('O','A') AND NOT tgisinternal) THEN
          RAISE EXCEPTION 'Native payment producer is incomplete' USING ERRCODE='42501';
        END IF;
      END LOOP;
      RETURN proof;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.payment_account_financial_state(text,timestamptz) FROM PUBLIC")


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("SELECT public.account_assert_guards_removable()")
    op.execute("DROP FUNCTION public.payment_account_financial_state(text,timestamptz)")
