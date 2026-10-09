"""Tenant-scoped immutable USDC log facts and guarded transfer progress."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "payment_service_0058_transfers"
down_revision = "payment_service_0057_intents"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_usdc_intent_recipient",
        "usdc_payment_intents",
        ["id", "tenant_id", "user_id", "chain_id", "deposit_address"],
    )
    op.create_table(
        "usdc_chain_transfers",
        sa.Column("chain_id", sa.Integer(), primary_key=True),
        sa.Column("tx_hash", sa.String(66), primary_key=True),
        sa.Column("log_index", sa.BigInteger(), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=False),
        sa.Column("block_hash", sa.String(66), nullable=False),
        sa.Column("from_address", sa.String(42), nullable=False),
        sa.Column("to_address", sa.String(42), nullable=False),
        sa.Column("amount_atoms", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(32), server_default="seen", nullable=False),
        sa.Column("intent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id", "chain_id", "to_address"],
            [
                "usdc_deposit_addresses.tenant_id",
                "usdc_deposit_addresses.user_id",
                "usdc_deposit_addresses.chain_id",
                "usdc_deposit_addresses.address",
            ],
            ondelete="RESTRICT",
            name="fk_usdc_transfer_destination",
        ),
        sa.ForeignKeyConstraint(
            ["intent_id", "tenant_id", "user_id", "chain_id", "to_address"],
            [
                "usdc_payment_intents.id",
                "usdc_payment_intents.tenant_id",
                "usdc_payment_intents.user_id",
                "usdc_payment_intents.chain_id",
                "usdc_payment_intents.deposit_address",
            ],
            ondelete="RESTRICT",
            name="fk_usdc_transfer_intent",
        ),
        sa.CheckConstraint("chain_id IN (8453, 84532)", name="ck_usdc_transfer_chain"),
        sa.CheckConstraint(
            "log_index >= 0 AND block_number >= 0 AND amount_atoms > 0",
            name="ck_usdc_transfer_values",
        ),
        sa.CheckConstraint(
            "tx_hash ~ '^0x[0-9a-f]{64}$' AND block_hash ~ '^0x[0-9a-f]{64}$'",
            name="ck_usdc_transfer_hashes",
        ),
        sa.CheckConstraint(
            "from_address ~ '^0x[0-9a-f]{40}$' AND to_address ~ '^0x[0-9a-f]{40}$'",
            name="ck_usdc_transfer_addresses",
        ),
        sa.CheckConstraint(
            "status IN ('seen', 'credited', 'final', 'reorged')",
            name="ck_usdc_transfer_status",
        ),
    )
    op.execute("ALTER TABLE usdc_chain_transfers ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE usdc_chain_transfers FORCE ROW LEVEL SECURITY")
    predicate = (
        "tenant_id::text = nullif(current_setting('app.current_tenant_id', true), '')"
    )
    for operation in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        clause = (
            f"WITH CHECK ({predicate})"
            if operation == "INSERT"
            else f"USING ({predicate})"
        )
        if operation == "UPDATE":
            clause += f" WITH CHECK ({predicate})"
        op.execute(
            f"CREATE POLICY usdc_transfer_{operation.lower()} ON usdc_chain_transfers FOR {operation} {clause}"
        )
    op.execute("""
    CREATE FUNCTION public.usdc_transfer_progress_only() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    BEGIN
      IF (to_jsonb(NEW) - 'status' - 'intent_id') IS DISTINCT FROM
         (to_jsonb(OLD) - 'status' - 'intent_id') OR
         (OLD.intent_id IS NOT NULL AND NEW.intent_id IS DISTINCT FROM (OLD.intent_id)) OR
         (OLD.status IN ('final', 'reorged') AND NEW.status <> OLD.status) OR
         (OLD.status = 'credited' AND NEW.status = 'seen') THEN
        RAISE EXCEPTION 'USDC transfer history cannot be rewritten' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER usdc_transfer_progress BEFORE UPDATE ON public.usdc_chain_transfers
      FOR EACH ROW EXECUTE FUNCTION public.usdc_transfer_progress_only();
    CREATE TRIGGER usdc_transfer_delete BEFORE DELETE ON public.usdc_chain_transfers
      FOR EACH ROW EXECUTE FUNCTION public.usdc_journal_immutable();
    CREATE TRIGGER usdc_transfer_truncate BEFORE TRUNCATE ON public.usdc_chain_transfers
      FOR EACH STATEMENT EXECUTE FUNCTION public.usdc_journal_immutable();
    """)


def downgrade():
    op.execute("SET LOCAL row_security = off")
    op.execute("LOCK TABLE public.usdc_chain_transfers IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM public.usdc_chain_transfers) THEN
            RAISE EXCEPTION 'Cannot remove nonempty USDC transfer history';
        END IF;
    END $$;""")
    op.drop_table("usdc_chain_transfers")
    op.execute("DROP FUNCTION public.usdc_transfer_progress_only()")
    op.drop_constraint(
        "uq_usdc_intent_recipient", "usdc_payment_intents", type_="unique"
    )
