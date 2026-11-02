"""One-use host-control challenges and immutable collector receipts."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "payment_service_0067_controls"
down_revision = "payment_service_0066_fiat"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "connect_control_proofs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("host_org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("enrollment_attempt_id", UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", sa.String(255), nullable=False),
        sa.Column("bank_id", sa.String(255), nullable=False),
        sa.Column("owner_sub", sa.String(512), nullable=False),
        sa.Column("challenge_nonce", sa.String(64), nullable=False),
        sa.Column("ownership_snapshot", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report", JSONB(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "challenge_nonce ~ '^[0-9a-f]{64}$'", name="ck_control_nonce"
        ),
        sa.CheckConstraint(
            "length(trim(owner_sub)) BETWEEN 1 AND 512", name="ck_control_owner"
        ),
        sa.CheckConstraint(
            "account_id ~ '^acct_[A-Za-z0-9]+$'", name="ck_control_account"
        ),
        sa.CheckConstraint("bank_id ~ '^ba_[A-Za-z0-9]+$'", name="ck_control_bank"),
        sa.CheckConstraint(
            "expires_at > created_at AND expires_at <= created_at + interval '5 minutes'",
            name="ck_control_lifetime",
        ),
        sa.CheckConstraint(
            "(report IS NULL AND accepted_at IS NULL) OR (report IS NOT NULL AND accepted_at IS NOT NULL AND accepted_at >= created_at AND accepted_at <= expires_at)",
            name="ck_control_accepted",
        ),
        sa.UniqueConstraint("challenge_nonce", name="uq_control_nonce"),
    )
    op.create_index(
        "ix_connect_control_proofs_tenant_id", "connect_control_proofs", ["tenant_id"]
    )
    op.execute("ALTER TABLE connect_control_proofs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE connect_control_proofs FORCE ROW LEVEL SECURITY")
    condition = (
        "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
    )
    for operation, clause in (
        ("SELECT", f"USING ({condition})"),
        ("DELETE", f"USING ({condition})"),
        ("INSERT", f"WITH CHECK ({condition})"),
        ("UPDATE", f"USING ({condition}) WITH CHECK ({condition})"),
    ):
        op.execute(
            f"CREATE POLICY control_proof_{operation.lower()} ON connect_control_proofs FOR {operation} {clause}"
        )
    op.execute("""
    CREATE FUNCTION public.control_proof_once() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    BEGIN
      IF OLD.report IS NOT NULL OR NEW.report IS NULL OR NEW.accepted_at IS NULL OR
         (to_jsonb(NEW) - 'report' - 'accepted_at') IS DISTINCT FROM
         (to_jsonb(OLD) - 'report' - 'accepted_at') THEN
        RAISE EXCEPTION 'Host-control proof history is immutable' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER control_proof_update BEFORE UPDATE ON public.connect_control_proofs FOR EACH ROW EXECUTE FUNCTION public.control_proof_once();
    CREATE TRIGGER control_proof_delete BEFORE DELETE ON public.connect_control_proofs FOR EACH ROW EXECUTE FUNCTION public.connect_recipient_immutable();
    CREATE TRIGGER control_proof_truncate BEFORE TRUNCATE ON public.connect_control_proofs FOR EACH STATEMENT EXECUTE FUNCTION public.connect_recipient_immutable();
    """)


def downgrade():
    op.execute("SET LOCAL row_security = off")
    op.execute("LOCK TABLE public.connect_control_proofs IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM public.connect_control_proofs) THEN
        RAISE EXCEPTION 'Cannot remove nonempty host-control proof history';
      END IF;
    END $$;""")
    op.drop_table("connect_control_proofs")
    op.execute("DROP FUNCTION public.control_proof_once()")
