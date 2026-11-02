"""Payment-owned deposit destinations and unpaid intent uniqueness."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "payment_service_0057_intents"
down_revision = "payment_service_0056_journal"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "usdc_deposit_addresses",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chain_id", sa.Integer(), primary_key=True),
        sa.Column(
            "hd_index",
            sa.Integer(),
            sa.Identity(
                always=True, start=0, minvalue=0, maxvalue=2147483647, cycle=False
            ),
            nullable=False,
        ),
        sa.Column("address", sa.String(42), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("chain_id", "user_id", name="uq_usdc_deposit_user"),
        sa.UniqueConstraint("chain_id", "address", name="uq_usdc_deposit_address"),
        sa.UniqueConstraint("hd_index", name="uq_usdc_deposit_index"),
        sa.UniqueConstraint(
            "tenant_id", "user_id", "chain_id", "address", name="uq_usdc_deposit_scope"
        ),
        sa.CheckConstraint("chain_id IN (8453, 84532)", name="ck_usdc_deposit_chain"),
        sa.CheckConstraint("hd_index >= 0", name="ck_usdc_deposit_index"),
        sa.CheckConstraint(
            "address ~ '^0x[0-9a-f]{40}$' AND address <> '0x0000000000000000000000000000000000000000'",
            name="ck_usdc_deposit_address",
        ),
    )
    op.create_table(
        "usdc_payment_intents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lease_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("deposit_address", sa.String(42), nullable=False),
        sa.Column("amount_atoms", sa.BigInteger(), nullable=False),
        sa.Column(
            "received_atoms", sa.BigInteger(), server_default="0", nullable=False
        ),
        sa.Column("status", sa.String(32), server_default="open", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id", "chain_id", "deposit_address"],
            [
                "usdc_deposit_addresses.tenant_id",
                "usdc_deposit_addresses.user_id",
                "usdc_deposit_addresses.chain_id",
                "usdc_deposit_addresses.address",
            ],
            ondelete="RESTRICT",
            name="fk_usdc_intent_deposit_scope",
        ),
        sa.UniqueConstraint(
            "tenant_id", "chain_id", "lease_id", name="uq_usdc_intent_lease"
        ),
        sa.UniqueConstraint("id", "tenant_id", "chain_id", name="uq_usdc_intent_scope"),
        sa.CheckConstraint(
            "amount_atoms > 0 AND received_atoms >= 0", name="ck_usdc_intent_atoms"
        ),
        sa.CheckConstraint("expires_at > created_at", name="ck_usdc_intent_expiry"),
        sa.CheckConstraint(
            "status IN ('open', 'partially_paid', 'paid', 'expired', 'cancelled')",
            name="ck_usdc_intent_status",
        ),
        sa.CheckConstraint(
            "(status <> 'open' OR received_atoms = 0) AND (status <> 'partially_paid' OR (received_atoms > 0 AND received_atoms < amount_atoms)) AND (status <> 'paid' OR received_atoms >= amount_atoms)",
            name="ck_usdc_intent_progress",
        ),
    )
    op.create_index(
        "uq_usdc_intent_unpaid",
        "usdc_payment_intents",
        ["chain_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('open', 'partially_paid')"),
    )
    for table in ("usdc_deposit_addresses", "usdc_payment_intents"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        predicate = "tenant_id::text = nullif(current_setting('app.current_tenant_id', true), '')"
        for operation in ("SELECT", "INSERT", "UPDATE", "DELETE"):
            clause = (
                f"WITH CHECK ({predicate})"
                if operation == "INSERT"
                else f"USING ({predicate})"
            )
            if operation == "UPDATE":
                clause += f" WITH CHECK ({predicate})"
            op.execute(
                f"CREATE POLICY {table}_{operation.lower()} ON {table} FOR {operation} {clause}"
            )
        op.execute(
            f"CREATE TRIGGER {table}_delete BEFORE DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION public.usdc_journal_immutable()"
        )
        op.execute(
            f"CREATE TRIGGER {table}_truncate BEFORE TRUNCATE ON {table} FOR EACH STATEMENT EXECUTE FUNCTION public.usdc_journal_immutable()"
        )
    op.execute(
        "CREATE TRIGGER usdc_deposit_immutable BEFORE UPDATE ON usdc_deposit_addresses FOR EACH ROW EXECUTE FUNCTION public.usdc_journal_immutable()"
    )

    op.execute("""
    CREATE FUNCTION public.usdc_intent_progress_only() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    BEGIN
      IF (to_jsonb(NEW) - 'status' - 'received_atoms') IS DISTINCT FROM
         (to_jsonb(OLD) - 'status' - 'received_atoms') OR
         NEW.received_atoms < OLD.received_atoms OR
         (OLD.status IN ('paid', 'expired', 'cancelled') AND
          (NEW.status <> OLD.status OR NEW.received_atoms <> OLD.received_atoms)) OR
         (OLD.status = 'partially_paid' AND NEW.status = 'open') THEN
        RAISE EXCEPTION 'USDC intent history cannot be rewritten' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER usdc_intent_progress BEFORE UPDATE ON public.usdc_payment_intents
      FOR EACH ROW EXECUTE FUNCTION public.usdc_intent_progress_only();
    """)


def downgrade():
    # A non-BYPASSRLS migrator fails closed rather than hiding financial records.
    op.execute("SET LOCAL row_security = off")
    op.execute(
        "LOCK TABLE public.usdc_deposit_addresses, public.usdc_payment_intents IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM public.usdc_deposit_addresses) OR EXISTS (SELECT 1 FROM public.usdc_payment_intents) THEN
            RAISE EXCEPTION 'Cannot remove nonempty USDC payment records';
        END IF;
    END $$;""")
    op.drop_table("usdc_payment_intents")
    op.drop_table("usdc_deposit_addresses")
    op.execute("DROP FUNCTION public.usdc_intent_progress_only()")
