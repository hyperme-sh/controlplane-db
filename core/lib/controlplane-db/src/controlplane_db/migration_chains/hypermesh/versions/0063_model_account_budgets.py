"""Reserve shared account capacity across tenants, retaining soft-delete headroom."""

import sqlalchemy as sa
from alembic import op

revision = "hypermesh_0063_model_budget"
down_revision = "hypermesh_0062_model_lifecycle"
branch_labels = None
depends_on = None


def upgrade():
    # This operational aggregate contains only account/count, no tenant data.
    op.create_table(
        "hypermesh_model_account_budgets",
        sa.Column("account", sa.String(24), primary_key=True),
        sa.Column("reserved_entries", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("reserved_entries >= 0", name="ck_hm_account_entries"),
    )
    # Fail the migration if its privileged role cannot inventory every tenant;
    # silently applying tenant filtering here would under-reserve the account.
    op.execute("SET LOCAL row_security = off")
    op.execute("""INSERT INTO hypermesh_model_account_budgets (account, reserved_entries)
        SELECT storage_account, sum(jsonb_array_length(manifest) * 2)
        FROM hypermesh_model_revisions GROUP BY storage_account""")
    op.execute("SET LOCAL row_security = on")


def downgrade():
    raise RuntimeError("Disable model creation before removing account reservations")
