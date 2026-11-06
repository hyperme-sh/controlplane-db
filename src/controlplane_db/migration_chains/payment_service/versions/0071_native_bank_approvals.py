"""Immutable owner/MFA-approved banks for embedded control policy."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "payment_service_0071_bank_access"
down_revision = "payment_service_0070_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "connect_bank_approvals",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("host_org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("enrollment_attempt_id", UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", sa.String(255), nullable=False),
        sa.Column("platform_id", sa.String(255), nullable=False),
        sa.Column("bank_id", sa.String(255), nullable=False),
        sa.Column("owner_sub", sa.String(512), nullable=False),
        sa.Column("member_id", sa.String(512), nullable=False),
        sa.Column("epoch", sa.BigInteger(), nullable=False),
        sa.Column("policy_hashes", JSONB(), nullable=False),
        sa.Column("bank_observation", JSONB(), nullable=False),
        sa.Column("second_factor_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "host_org_id"],
            ["connect_access_states.tenant_id", "connect_access_states.host_org_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("epoch >= 1", name="ck_bank_approval_epoch"),
        sa.CheckConstraint(
            "account_id ~ '^acct_[A-Za-z0-9]+$' AND platform_id ~ '^acct_[A-Za-z0-9]+$' AND bank_id ~ '^ba_[A-Za-z0-9]+$' AND account_id <> platform_id",
            name="ck_bank_approval_native_ids",
        ),
        sa.CheckConstraint(
            "length(owner_sub) BETWEEN 1 AND 512 AND length(member_id) BETWEEN 1 AND 512",
            name="ck_bank_approval_actor",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(policy_hashes) = 'object' AND jsonb_typeof(bank_observation) = 'object'",
            name="ck_bank_approval_observations",
        ),
    )
    op.create_index(
        "ix_connect_bank_approvals_tenant_id", "connect_bank_approvals", ["tenant_id"]
    )
    op.execute("ALTER TABLE connect_bank_approvals ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE connect_bank_approvals FORCE ROW LEVEL SECURITY")
    condition = (
        "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
    )
    op.execute(
        f"CREATE POLICY bank_approval_select ON connect_bank_approvals FOR SELECT USING ({condition})"
    )
    op.execute(
        f"CREATE POLICY bank_approval_insert ON connect_bank_approvals FOR INSERT WITH CHECK ({condition})"
    )
    for operation in ("UPDATE", "DELETE", "TRUNCATE"):
        op.execute(
            f"CREATE TRIGGER connect_bank_approvals_{operation.lower()} BEFORE {operation} ON connect_bank_approvals FOR EACH {'STATEMENT' if operation == 'TRUNCATE' else 'ROW'} EXECUTE FUNCTION public.connect_recipient_immutable()"
        )


def downgrade():
    op.execute("SET LOCAL row_security=off")
    op.execute("LOCK TABLE connect_bank_approvals IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM connect_bank_approvals) THEN
        RAISE EXCEPTION 'Cannot remove approved bank history' USING ERRCODE='23514';
      END IF;
    END $$""")
    op.drop_table("connect_bank_approvals")
