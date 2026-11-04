"""Retain account debt observations independently of successful reversals."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from alembic import op

revision = "payment_service_0075_exposure"
down_revision = "payment_service_0074_live"
branch_labels = None
depends_on = None
TABLE = "connect_reversal_exposure_observations"


def upgrade():
    op.create_table(
        "connect_reversal_exposure_observations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("host_org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("lease_id", UUID(as_uuid=True), nullable=False),
        sa.Column("billing_record_id", UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", sa.String(255), nullable=False),
        sa.Column("platform_id", sa.String(255), nullable=False),
        sa.Column("transfer_id", sa.String(255), nullable=False),
        sa.Column("livemode", sa.Boolean(), nullable=False),
        sa.Column("reversed_cents", sa.BigInteger(), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("plan_digest", sa.String(64), nullable=False),
        sa.Column("status", sa.String(48), nullable=False),
        sa.Column("has_observed_debt", sa.Boolean(), nullable=False),
        sa.Column("observation", JSONB(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recheck_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["billing_record_id"], ["billing_records.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "host_org_id"],
            [
                "connect_recipient_accounts.tenant_id",
                "connect_recipient_accounts.host_org_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "status IN ('no_account_debt_observed', 'connected_debt_observed', 'review_required', 'unavailable')",
            name="ck_reversal_exposure_status",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "billing_record_id",
            "sequence",
            name="uq_reversal_exposure_sequence",
        ),
        sa.CheckConstraint("sequence > 0", name="ck_reversal_exposure_sequence"),
        sa.CheckConstraint("reversed_cents > 0", name="ck_reversal_exposure_amount"),
        sa.CheckConstraint(
            "length(plan_digest) = 64", name="ck_reversal_exposure_digest"
        ),
        sa.CheckConstraint(
            "jsonb_typeof(observation) = 'object'", name="ck_reversal_exposure_object"
        ),
        sa.CheckConstraint(
            "recheck_at >= recorded_at", name="ck_reversal_exposure_time"
        ),
    )
    op.create_index(
        "ix_reversal_exposure_latest",
        "connect_reversal_exposure_observations",
        ["tenant_id", "billing_record_id", "recorded_at", "id"],
    )
    op.execute(f"ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY")
    for action in ("SELECT", "INSERT"):
        predicate = "USING" if action == "SELECT" else "WITH CHECK"
        op.execute(
            f"CREATE POLICY reversal_exposure_{action.lower()} ON {TABLE} FOR {action} {predicate} (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)"
        )
    for action in ("UPDATE", "DELETE", "TRUNCATE"):
        each = "STATEMENT" if action == "TRUNCATE" else "ROW"
        op.execute(
            f"CREATE TRIGGER reversal_exposure_{action.lower()} BEFORE {action} ON {TABLE} FOR EACH {each} EXECUTE FUNCTION public.connect_recipient_immutable()"
        )
    op.execute(
        f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'controlplane_app') THEN GRANT SELECT, INSERT ON {TABLE} TO controlplane_app; END IF; END $$"
    )


def downgrade():
    op.execute(f"LOCK TABLE {TABLE} IN ACCESS EXCLUSIVE MODE")
    op.execute("SET LOCAL row_security = off")
    if (
        op.get_bind()
        .execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {TABLE})"))
        .scalar()
    ):
        raise RuntimeError("Cannot discard retained reversal exposure observations")
    op.drop_table("connect_reversal_exposure_observations")
