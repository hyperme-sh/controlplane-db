"""Recognize exact private TEST delete capabilities without changing normal guards."""

import re
from alembic import op
import sqlalchemy as sa

revision = "payment_service_0081_test_gc"
down_revision = "payment_service_0080_fin_state"
branch_labels = None
depends_on = None

PREFIX = """BEGIN
      IF TG_LEVEL='ROW' AND TG_OP='DELETE' AND
        public.account_test_row_delete_allowed(TG_RELID,to_jsonb(OLD)) THEN
        RETURN OLD;
      END IF;
"""


def upgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    op.execute("""CREATE TABLE public.account_test_delete_guard_originals (
      signature text PRIMARY KEY, definition text NOT NULL);
      ALTER TABLE public.account_test_delete_guard_originals ENABLE ROW LEVEL SECURITY;
      ALTER TABLE public.account_test_delete_guard_originals FORCE ROW LEVEL SECURITY;
      REVOKE ALL ON public.account_test_delete_guard_originals FROM PUBLIC;
    """)
    connection = op.get_bind()
    rows = (
        connection.execute(
            sa.text("""SELECT DISTINCT p.oid::regprocedure::text AS signature,
      p.prosrc AS body,pg_get_functiondef(p.oid) AS definition,l.lanname
      FROM pg_catalog.pg_trigger t JOIN pg_catalog.pg_proc p ON p.oid=t.tgfoid
      JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
      JOIN pg_catalog.pg_language l ON l.oid=p.prolang
      WHERE n.nspname='public' AND NOT t.tgisinternal AND (t.tgtype & 11)=11
        AND t.tgrelid IN (
          WITH RECURSIVE owned(rel) AS (
            SELECT c.oid FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace ns ON ns.oid=c.relnamespace
              WHERE ns.nspname='public' AND c.relname IN (
                'billing_records','hypermesh_leases','hypermesh_orders','hypermesh_payouts',
                'billing_tax_orders','billing_tax_calculations','connect_recipient_accounts',
                'connect_bank_approvals','connect_control_proofs','connect_reversal_exposure_observations',
                'connect_access_states','connect_access_grants','connect_access_results',
                'host_payout_addresses','payer_mismatch_accounts','usdc_ledger_postings',
                'usdc_payment_intents','usdc_outbound_transfers','usdc_chain_transfers','onramp_sessions')
            UNION SELECT f.conrelid FROM pg_catalog.pg_constraint f JOIN owned o ON f.confrelid=o.rel WHERE f.contype='f'
          ) SELECT rel FROM owned)

      ORDER BY signature""")
        )
        .mappings()
        .all()
    )
    if not rows:
        raise RuntimeError("Installed native delete guards required")
    for row in rows:
        if row["lanname"] != "plpgsql" or row["body"].count(
            "account_test_row_delete_allowed"
        ):
            raise RuntimeError("Unexpected native delete guard implementation")
        body, count = re.subn(r"(?im)^\s*BEGIN\b", PREFIX, row["body"], count=1)
        if count != 1 or row["definition"].count(row["body"]) != 1:
            raise RuntimeError("Native delete guard body cannot be preserved exactly")
        connection.execute(
            sa.text(
                "INSERT INTO public.account_test_delete_guard_originals VALUES(:s,:d)"
            ),
            {"s": row["signature"], "d": row["definition"]},
        )
        # Execute a trusted catalog definition, not a caller-supplied identifier.
        connection.exec_driver_sql(
            row["definition"].replace(row["body"], body, 1),
            execution_options={"no_parameters": True},
        )


def downgrade():
    op.execute("SELECT public.account_lock_financial_inventory_schema()")
    connection = op.get_bind()
    if connection.scalar(sa.text("SELECT public.account_test_data_enabled()")):
        raise RuntimeError(
            "Disable TEST policy before restoring original delete guards"
        )
    for definition in connection.scalars(
        sa.text(
            "SELECT definition FROM public.account_test_delete_guard_originals ORDER BY signature"
        )
    ):
        connection.exec_driver_sql(
            definition, execution_options={"no_parameters": True}
        )
    op.execute("DROP TABLE public.account_test_delete_guard_originals")
