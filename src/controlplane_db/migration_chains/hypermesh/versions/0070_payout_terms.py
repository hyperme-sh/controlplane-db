"""Keep original offer terms immutable; historical terms remain unknown."""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "hypermesh_0070_payout_terms"
down_revision = "hypermesh_0069_fee_binding"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hypermesh_leases", sa.Column("payout_terms", postgresql.JSONB(none_as_null=True), nullable=True))
    op.execute("""CREATE FUNCTION hm_payout_terms_immutable() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
        IF NEW.payout_terms IS DISTINCT FROM OLD.payout_terms THEN
            RAISE EXCEPTION 'Frozen payout terms cannot change';
        END IF;
        RETURN NEW;
    END $$""")
    op.execute("""CREATE TRIGGER payout_terms_immutable
        BEFORE UPDATE ON hypermesh_leases
        FOR EACH ROW EXECUTE FUNCTION hm_payout_terms_immutable()""")


def downgrade():
    raise RuntimeError("Original payout terms must not be discarded")
