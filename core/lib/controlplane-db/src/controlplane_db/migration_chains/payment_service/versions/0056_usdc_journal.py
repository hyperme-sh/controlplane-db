"""Tenant-scoped, balanced and immutable USDC journal postings."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "payment_service_0056_journal"
down_revision = "payment_service_0055_subject"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "usdc_ledger_postings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("ref_type", sa.String(128), nullable=False),
        sa.Column("ref_id", sa.String(512), nullable=False),
        sa.Column("sealed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "id", "tenant_id", "chain_id", name="uq_usdc_posting_scope"
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "chain_id",
            "ref_type",
            "ref_id",
            name="uq_usdc_posting_reference",
        ),
        sa.CheckConstraint("chain_id IN (8453, 84532)", name="ck_usdc_posting_chain"),
        sa.CheckConstraint(
            "length(trim(ref_type)) > 0 AND length(trim(ref_id)) > 0",
            name="ck_usdc_posting_reference",
        ),
    )
    op.create_table(
        "usdc_ledger_entries",
        sa.Column("posting_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("line_no", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=False),
        sa.Column("account", sa.String(768), nullable=False),
        sa.Column("amount_atoms", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["posting_id", "tenant_id", "chain_id"],
            [
                "usdc_ledger_postings.id",
                "usdc_ledger_postings.tenant_id",
                "usdc_ledger_postings.chain_id",
            ],
            ondelete="RESTRICT",
            name="fk_usdc_entry_scope",
        ),
        sa.CheckConstraint("line_no > 0", name="ck_usdc_entry_line"),
        sa.CheckConstraint("amount_atoms <> 0", name="ck_usdc_entry_amount"),
        sa.CheckConstraint("length(trim(account)) > 0", name="ck_usdc_entry_account"),
    )
    for table in ("usdc_ledger_postings", "usdc_ledger_entries"):
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
    op.execute("""
    CREATE FUNCTION public.usdc_journal_immutable() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    BEGIN
      RAISE EXCEPTION 'USDC journal records are immutable' USING ERRCODE = '23514';
    END $$;
    CREATE FUNCTION public.usdc_posting_seal_only() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    BEGIN
      IF OLD.sealed OR NOT NEW.sealed OR
         (to_jsonb(NEW) - 'sealed') IS DISTINCT FROM (to_jsonb(OLD) - 'sealed') THEN
        RAISE EXCEPTION 'Only sealing a draft USDC posting is allowed' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE FUNCTION public.usdc_entry_draft_only() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    DECLARE is_sealed boolean;
    BEGIN
      SELECT sealed INTO is_sealed FROM public.usdc_ledger_postings
      WHERE id = NEW.posting_id AND tenant_id = NEW.tenant_id AND chain_id = NEW.chain_id
      FOR UPDATE;
      IF NOT FOUND OR is_sealed THEN
        RAISE EXCEPTION 'USDC posting is not writable' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE FUNCTION public.usdc_posting_balanced() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    DECLARE is_sealed boolean; lines bigint; total numeric;
    BEGIN
      SELECT sealed INTO is_sealed FROM public.usdc_ledger_postings
      WHERE id = NEW.id AND tenant_id = NEW.tenant_id AND chain_id = NEW.chain_id;
      IF NOT FOUND OR NOT is_sealed THEN
        RAISE EXCEPTION 'USDC posting must be sealed before commit' USING ERRCODE = '23514';
      END IF;
      SELECT count(*), coalesce(sum(amount_atoms), 0) INTO lines, total
      FROM public.usdc_ledger_entries
      WHERE posting_id = NEW.id AND tenant_id = NEW.tenant_id AND chain_id = NEW.chain_id;
      IF lines < 2 OR total <> 0 THEN
        RAISE EXCEPTION 'USDC posting must have balanced entries' USING ERRCODE = '23514';
      END IF;
      RETURN NULL;
    END $$;
    CREATE TRIGGER usdc_posting_seal BEFORE UPDATE ON public.usdc_ledger_postings
      FOR EACH ROW EXECUTE FUNCTION public.usdc_posting_seal_only();
    CREATE TRIGGER usdc_posting_delete BEFORE DELETE ON public.usdc_ledger_postings
      FOR EACH ROW EXECUTE FUNCTION public.usdc_journal_immutable();
    CREATE TRIGGER usdc_posting_truncate BEFORE TRUNCATE ON public.usdc_ledger_postings
      FOR EACH STATEMENT EXECUTE FUNCTION public.usdc_journal_immutable();
    CREATE TRIGGER usdc_entry_insert BEFORE INSERT ON public.usdc_ledger_entries
      FOR EACH ROW EXECUTE FUNCTION public.usdc_entry_draft_only();
    CREATE TRIGGER usdc_entry_modify BEFORE UPDATE OR DELETE ON public.usdc_ledger_entries
      FOR EACH ROW EXECUTE FUNCTION public.usdc_journal_immutable();
    CREATE TRIGGER usdc_entry_truncate BEFORE TRUNCATE ON public.usdc_ledger_entries
      FOR EACH STATEMENT EXECUTE FUNCTION public.usdc_journal_immutable();
    CREATE CONSTRAINT TRIGGER usdc_posting_balance AFTER INSERT OR UPDATE ON public.usdc_ledger_postings
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.usdc_posting_balanced();
    """)


def downgrade():
    # Financial records cannot be discarded by a schema rollback.
    op.execute("SET LOCAL row_security = off")
    op.execute(
        "LOCK TABLE public.usdc_ledger_postings, public.usdc_ledger_entries IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM public.usdc_ledger_postings) THEN
        RAISE EXCEPTION 'Cannot remove a nonempty USDC journal';
      END IF;
    END $$;""")
    op.drop_table("usdc_ledger_entries")
    op.drop_table("usdc_ledger_postings")
    for function in (
        "usdc_posting_balanced",
        "usdc_entry_draft_only",
        "usdc_posting_seal_only",
        "usdc_journal_immutable",
    ):
        op.execute(f"DROP FUNCTION public.{function}()")
