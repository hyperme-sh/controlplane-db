"""Retire unused custody tables; never discard financial or onramp history.

The USD billing/Connect attempt records remain authoritative. A second ledger
would duplicate those records; the unused chain/atom journal is removed instead.
"""

from importlib import import_module

from alembic import op

revision = "payment_service_0064_retire"
down_revision = "payment_service_0063_tax"
branch_labels = None
depends_on = None

TABLES = (
    "onramp_sessions",
    "usdc_outbound_transfers",
    "usdc_chain_transfers",
    "usdc_payment_intents",
    "usdc_deposit_addresses",
    "usdc_ledger_entries",
    "usdc_ledger_postings",
)
FUNCTIONS = (
    "onramp_progress_only",
    "usdc_outbound_progress_only",
    "usdc_transfer_progress_only",
    "usdc_intent_progress_only",
    "usdc_posting_balanced",
    "usdc_entry_draft_only",
    "usdc_posting_seal_only",
    "usdc_journal_immutable",
)


def upgrade():
    # Lock every table before testing any of them; no writer can race the guard.
    # row_security=off refuses non-bypass roles rather than hiding tenant rows.
    op.execute("SET LOCAL row_security = off")
    op.execute("""
        LOCK TABLE public.onramp_sessions, public.usdc_outbound_transfers,
          public.usdc_chain_transfers, public.usdc_payment_intents,
          public.usdc_deposit_addresses, public.usdc_ledger_entries,
          public.usdc_ledger_postings IN ACCESS EXCLUSIVE MODE
    """)
    # The owning migrator must inspect every row, including other tenants.
    # The locks cover both this guard and the drop; failure rolls the DDL back.
    for table in TABLES:
        op.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM public.onramp_sessions)
            OR EXISTS (SELECT 1 FROM public.usdc_outbound_transfers)
            OR EXISTS (SELECT 1 FROM public.usdc_chain_transfers)
            OR EXISTS (SELECT 1 FROM public.usdc_payment_intents)
            OR EXISTS (SELECT 1 FROM public.usdc_deposit_addresses)
            OR EXISTS (SELECT 1 FROM public.usdc_ledger_entries)
            OR EXISTS (SELECT 1 FROM public.usdc_ledger_postings) THEN
            RAISE EXCEPTION 'Cannot retire nonempty custody or legacy onramp history';
          END IF;
        END $$;
    """)
    # Dependency order, without CASCADE: unrelated records cannot be removed.
    op.drop_table("onramp_sessions")
    op.drop_table("usdc_outbound_transfers")
    op.drop_table("usdc_chain_transfers")
    op.drop_table("usdc_payment_intents")
    op.drop_table("usdc_deposit_addresses")
    op.drop_table("usdc_ledger_entries")
    op.drop_table("usdc_ledger_postings")
    for function in FUNCTIONS:
        op.execute(f"DROP FUNCTION public.{function}()")


def downgrade():
    # Recreate only the empty historical schema using the unchanged revisions.
    for module in (
        "0056_usdc_journal",
        "0057_usdc_intents",
        "0058_usdc_transfers",
        "0059_usdc_outbound",
        "0060_onramp_sessions",
    ):
        import_module(
            "controlplane_db.migration_chains.payment_service.versions." + module
        ).upgrade()
