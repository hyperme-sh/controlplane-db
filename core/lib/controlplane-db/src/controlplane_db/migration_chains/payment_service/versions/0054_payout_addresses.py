"""Payment-owned Base payout destinations and verification evidence."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "payment_service_0054_payout_addr"
down_revision = "payment_service_0053_baseline"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "host_payout_addresses",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("host_org_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("chain_id", sa.Integer(), primary_key=True),
        sa.Column("address", sa.String(42), nullable=False),
        sa.Column("verified_by_sub", sa.String(256), nullable=False),
        sa.Column("proof_audience", sa.String(256), nullable=False),
        sa.Column("proof_message_hash", sa.String(64), nullable=False),
        sa.Column("proof_signature_hash", sa.String(64), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "chain_id IN (8453, 84532)", name="ck_payout_address_base_chain"
        ),
        sa.CheckConstraint(
            "address ~ '^0x[0-9a-fA-F]{40}$'", name="ck_payout_address_hex"
        ),
        sa.CheckConstraint(
            "length(verified_by_sub) BETWEEN 1 AND 256",
            name="ck_payout_address_subject",
        ),
        sa.CheckConstraint(
            "length(proof_audience) BETWEEN 1 AND 256",
            name="ck_payout_address_audience",
        ),
        sa.CheckConstraint(
            "proof_message_hash ~ '^[0-9a-f]{64}$'", name="ck_payout_message_hash"
        ),
        sa.CheckConstraint(
            "proof_signature_hash ~ '^[0-9a-f]{64}$'", name="ck_payout_signature_hash"
        ),
    )
    op.execute("ALTER TABLE host_payout_addresses ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE host_payout_addresses FORCE ROW LEVEL SECURITY")
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
            f"CREATE POLICY tenant_isolation_{operation.lower()} ON host_payout_addresses FOR {operation} {clause}"
        )


def downgrade():
    op.drop_table("host_payout_addresses")
