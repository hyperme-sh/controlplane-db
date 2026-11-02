"""Payment-owned outbound instructions, idempotency and nonce reservations."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "payment_service_0059_outbound"
down_revision = "payment_service_0058_transfers"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "usdc_outbound_transfers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("asset", sa.String(16), nullable=False),
        sa.Column("from_address", sa.String(42), nullable=False),
        sa.Column("to_address", sa.String(42), nullable=False),
        sa.Column("amount_atoms", sa.BigInteger(), nullable=False),
        sa.Column("idempotency_key", sa.String(512), nullable=False),
        sa.Column("nonce", sa.BigInteger(), nullable=True),
        sa.Column("tx_hash", sa.String(66), nullable=True),
        sa.Column("status", sa.String(32), server_default="queued", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "tenant_id", "chain_id", "idempotency_key", name="uq_usdc_outbound_request"
        ),
        sa.UniqueConstraint(
            "chain_id", "from_address", "nonce", name="uq_usdc_outbound_nonce"
        ),
        sa.UniqueConstraint("chain_id", "tx_hash", name="uq_usdc_outbound_transaction"),
        sa.CheckConstraint("chain_id IN (8453, 84532)", name="ck_usdc_outbound_chain"),
        sa.CheckConstraint(
            "amount_atoms > 0 AND (nonce IS NULL OR nonce >= 0)",
            name="ck_usdc_outbound_values",
        ),
        sa.CheckConstraint(
            "length(trim(idempotency_key)) > 0", name="ck_usdc_outbound_request"
        ),
        sa.CheckConstraint(
            "from_address ~ '^0x[0-9a-f]{40}$' AND from_address <> '0x0000000000000000000000000000000000000000' AND to_address ~ '^0x[0-9a-f]{40}$' AND to_address <> '0x0000000000000000000000000000000000000000'",
            name="ck_usdc_outbound_addresses",
        ),
        sa.CheckConstraint(
            "tx_hash IS NULL OR tx_hash ~ '^0x[0-9a-f]{64}$'",
            name="ck_usdc_outbound_hash",
        ),
        sa.CheckConstraint(
            "(kind IN ('refund', 'payout', 'sweep') AND asset = 'usdc') OR (kind = 'gas_topup' AND asset = 'eth')",
            name="ck_usdc_outbound_asset",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'broadcast', 'confirmed', 'final', 'failed')",
            name="ck_usdc_outbound_status",
        ),
        sa.CheckConstraint(
            "(status <> 'queued' OR tx_hash IS NULL) AND (status NOT IN ('broadcast', 'confirmed', 'final') OR (nonce IS NOT NULL AND tx_hash IS NOT NULL)) AND (tx_hash IS NULL OR nonce IS NOT NULL)",
            name="ck_usdc_outbound_progress",
        ),
    )
    op.execute("ALTER TABLE usdc_outbound_transfers ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE usdc_outbound_transfers FORCE ROW LEVEL SECURITY")
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
            f"CREATE POLICY usdc_outbound_{operation.lower()} ON usdc_outbound_transfers FOR {operation} {clause}"
        )
    op.execute("""
    CREATE FUNCTION public.usdc_outbound_progress_only() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    BEGIN
      IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'queued' OR NEW.nonce IS NOT NULL OR NEW.tx_hash IS NOT NULL THEN
          RAISE EXCEPTION 'USDC outbound instructions must begin queued without transaction evidence' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
      END IF;
      IF (to_jsonb(NEW) - 'status' - 'nonce' - 'tx_hash') IS DISTINCT FROM
         (to_jsonb(OLD) - 'status' - 'nonce' - 'tx_hash') OR
         (OLD.nonce IS NOT NULL AND NEW.nonce IS DISTINCT FROM (OLD.nonce)) OR
         (OLD.tx_hash IS NOT NULL AND NEW.tx_hash IS DISTINCT FROM (OLD.tx_hash)) OR
         (OLD.status IN ('final', 'failed') AND to_jsonb(NEW) IS DISTINCT FROM (to_jsonb(OLD))) OR
         (NEW.status <> OLD.status AND NOT (
            (OLD.status = 'queued' AND NEW.status IN ('broadcast', 'failed')) OR
            (OLD.status = 'broadcast' AND NEW.status IN ('confirmed', 'failed')) OR
            (OLD.status = 'confirmed' AND NEW.status IN ('final', 'failed'))
         )) THEN
        RAISE EXCEPTION 'USDC outbound history cannot be rewritten' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER usdc_outbound_progress BEFORE INSERT OR UPDATE ON public.usdc_outbound_transfers
      FOR EACH ROW EXECUTE FUNCTION public.usdc_outbound_progress_only();
    CREATE TRIGGER usdc_outbound_delete BEFORE DELETE ON public.usdc_outbound_transfers
      FOR EACH ROW EXECUTE FUNCTION public.usdc_journal_immutable();
    CREATE TRIGGER usdc_outbound_truncate BEFORE TRUNCATE ON public.usdc_outbound_transfers
      FOR EACH STATEMENT EXECUTE FUNCTION public.usdc_journal_immutable();
    """)


def downgrade():
    # A migrator without BYPASSRLS fails closed under forced RLS.
    op.execute("SET LOCAL row_security = off")
    op.execute("LOCK TABLE public.usdc_outbound_transfers IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM public.usdc_outbound_transfers) THEN
            RAISE EXCEPTION 'Cannot remove nonempty USDC outbound history';
        END IF;
    END $$;""")
    op.drop_table("usdc_outbound_transfers")
    op.execute("DROP FUNCTION public.usdc_outbound_progress_only()")
