"""Flagged requests from automated safety screening, kept for operator review.

Only flagged requests are stored. Rows are tenant scoped with forced row level
security. The retention sweep deletes a row one year after its review is
closed, or one year after it was created when it is never reviewed; a delete
policy limited to expired rows lets the sweep run without enumerating tenants.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "hypermesh_0058_safety_flags"
down_revision = "hypermesh_0057_lease_usdc"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hypermesh_safety_flags",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("gateway_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lease_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("subject", sa.String(256), nullable=False),
        sa.Column("door", sa.String(16), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("rule_id", sa.String(128), nullable=False),
        sa.Column("classifier_version", sa.String(64), nullable=False),
        sa.Column("flagged_text", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(256), nullable=True),
        sa.Column("review_outcome", sa.String(32), nullable=True),
        sa.CheckConstraint(
            "category IN ('csam', 'self_harm', 'malware_intrusion', 'violent_extremism')",
            name="ck_hypermesh_safety_flag_category",
        ),
        sa.CheckConstraint(
            "action IN ('allow', 'block')", name="ck_hypermesh_safety_flag_action"
        ),
        sa.CheckConstraint("door IN ('chat', 'ir')", name="ck_hypermesh_safety_flag_door"),
        sa.CheckConstraint(
            "(review_closed_at IS NULL AND reviewed_by IS NULL AND review_outcome IS NULL) OR "
            "(review_closed_at IS NOT NULL AND reviewed_by IS NOT NULL AND review_outcome IN "
            "('no_action', 'actioned', 'false_positive'))",
            name="ck_hypermesh_safety_flag_review",
        ),
        sa.CheckConstraint(
            "length(flagged_text) <= 16384", name="ck_hypermesh_safety_flag_text"
        ),
    )
    op.create_index(
        "ix_hypermesh_safety_flags_open",
        "hypermesh_safety_flags",
        ["tenant_id", "created_at"],
    )
    op.create_index(
        "ix_hypermesh_safety_flags_retention",
        "hypermesh_safety_flags",
        [sa.text("coalesce(review_closed_at, created_at)")],
    )
    op.execute("ALTER TABLE hypermesh_safety_flags ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE hypermesh_safety_flags FORCE ROW LEVEL SECURITY")
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
            f"CREATE POLICY tenant_isolation_{operation.lower()} ON hypermesh_safety_flags "
            f"FOR {operation} {clause}"
        )
    # The retention sweep runs without a tenant. These policies match only
    # rows already past retention, and only in a transaction that set
    # app.safety_flag_retention. PostgreSQL applies SELECT policies to the
    # rows a DELETE ... WHERE reads, so the sweep needs both.
    expired = (
        "current_setting('app.safety_flag_retention', true) = 'on' "
        "AND coalesce(review_closed_at, created_at) < now() - interval '365 days'"
    )
    for operation in ("SELECT", "DELETE"):
        op.execute(
            f"CREATE POLICY safety_flag_retention_{operation.lower()} ON hypermesh_safety_flags "
            f"FOR {operation} USING ({expired})"
        )


def downgrade():
    # Flagged records are review evidence; dropping them is the explicit intent
    # of a downgrade, and earlier code never reads this table.
    op.drop_table("hypermesh_safety_flags")
