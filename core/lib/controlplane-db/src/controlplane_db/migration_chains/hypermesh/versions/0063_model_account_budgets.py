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
    # Revisions whose cleanup completed no longer hold account entries.
    op.execute("SET LOCAL row_security = off")
    op.execute("""INSERT INTO hypermesh_model_account_budgets (account, reserved_entries)
        SELECT storage_account, sum(jsonb_array_length(manifest) * 2)
        FROM hypermesh_model_revisions
        WHERE state <> 'deleted' GROUP BY storage_account""")
    op.execute("SET LOCAL row_security = on")
    # Revision rows can also disappear through a tenant cascade, which never
    # reaches the cleanup path. Release their entries when such a row is
    # deleted before its cleanup completed.
    op.execute("""CREATE OR REPLACE FUNCTION hm_release_model_account_entries() RETURNS trigger AS $$
        BEGIN
            IF OLD.state <> 'deleted' THEN
                UPDATE hypermesh_model_account_budgets
                SET reserved_entries = greatest(reserved_entries - jsonb_array_length(OLD.manifest) * 2, 0)
                WHERE account = OLD.storage_account;
            END IF;
            RETURN OLD;
        END $$ LANGUAGE plpgsql""")
    op.execute("DROP TRIGGER IF EXISTS hm_model_revision_release_entries ON hypermesh_model_revisions")
    op.execute("""CREATE TRIGGER hm_model_revision_release_entries BEFORE DELETE
        ON hypermesh_model_revisions FOR EACH ROW EXECUTE FUNCTION hm_release_model_account_entries()""")


def downgrade():
    raise RuntimeError("Disable model creation before removing account reservations")
