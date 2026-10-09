"""Payment-owned onramp session progress; provider events never credit intents."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "payment_service_0060_onramp"
down_revision = "payment_service_0059_outbound"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_usdc_intent_onramp_scope",
        "usdc_payment_intents",
        ["id", "tenant_id", "user_id", "chain_id"],
    )
    op.create_table(
        "onramp_sessions",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("intent_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("livemode", sa.Boolean(), nullable=False),
        sa.Column("destination_amount_atoms", sa.BigInteger(), nullable=False),
        sa.Column("fulfilled_amount_atoms", sa.BigInteger(), nullable=True),
        sa.Column("transaction_id", sa.String(66), nullable=True),
        sa.Column(
            "status", sa.String(32), server_default="initialized", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["intent_id", "tenant_id", "user_id", "chain_id"],
            [
                "usdc_payment_intents.id",
                "usdc_payment_intents.tenant_id",
                "usdc_payment_intents.user_id",
                "usdc_payment_intents.chain_id",
            ],
            name="fk_onramp_intent_scope",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("id ~ '^cos_[A-Za-z0-9]+$'", name="ck_onramp_id"),
        sa.CheckConstraint(
            "(chain_id = 8453 AND livemode) OR (chain_id = 84532 AND NOT livemode)",
            name="ck_onramp_mode",
        ),
        sa.CheckConstraint("destination_amount_atoms > 0", name="ck_onramp_amount"),
        sa.CheckConstraint(
            "status IN ('initialized', 'requires_payment', 'fulfillment_processing', 'fulfillment_complete', 'rejected')",
            name="ck_onramp_status",
        ),
        sa.CheckConstraint(
            "(status = 'fulfillment_complete' AND transaction_id ~ '^0x[0-9a-f]{64}$' AND transaction_id IS NOT NULL AND fulfilled_amount_atoms IS NOT NULL AND fulfilled_amount_atoms > 0) OR (status <> 'fulfillment_complete' AND transaction_id IS NULL AND fulfilled_amount_atoms IS NULL)",
            name="ck_onramp_evidence",
        ),
    )
    op.execute("ALTER TABLE onramp_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE onramp_sessions FORCE ROW LEVEL SECURITY")
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
            f"CREATE POLICY onramp_{operation.lower()} ON onramp_sessions FOR {operation} {clause}"
        )
    op.execute("""
    CREATE FUNCTION public.onramp_progress_only() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    BEGIN
      IF (to_jsonb(NEW) - 'status' - 'transaction_id' - 'fulfilled_amount_atoms') IS DISTINCT FROM
         (to_jsonb(OLD) - 'status' - 'transaction_id' - 'fulfilled_amount_atoms') OR
         (OLD.status IN ('fulfillment_complete', 'rejected') AND to_jsonb(NEW) IS DISTINCT FROM (to_jsonb(OLD))) OR
         (OLD.status = 'requires_payment' AND NEW.status = 'initialized') OR
         (OLD.status = 'fulfillment_processing' AND NEW.status IN ('initialized', 'requires_payment')) THEN
        RAISE EXCEPTION 'Onramp history cannot be rewritten' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER onramp_progress BEFORE UPDATE ON public.onramp_sessions FOR EACH ROW EXECUTE FUNCTION public.onramp_progress_only();
    CREATE TRIGGER onramp_delete BEFORE DELETE ON public.onramp_sessions FOR EACH ROW EXECUTE FUNCTION public.usdc_journal_immutable();
    CREATE TRIGGER onramp_truncate BEFORE TRUNCATE ON public.onramp_sessions FOR EACH STATEMENT EXECUTE FUNCTION public.usdc_journal_immutable();
    """)


def downgrade():
    op.execute("SET LOCAL row_security = off")
    op.execute("LOCK TABLE public.onramp_sessions IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM public.onramp_sessions) THEN
            RAISE EXCEPTION 'Cannot remove nonempty onramp history';
        END IF;
    END $$;""")
    op.drop_table("onramp_sessions")
    op.execute("DROP FUNCTION public.onramp_progress_only()")
    op.drop_constraint(
        "uq_usdc_intent_onramp_scope", "usdc_payment_intents", type_="unique"
    )
