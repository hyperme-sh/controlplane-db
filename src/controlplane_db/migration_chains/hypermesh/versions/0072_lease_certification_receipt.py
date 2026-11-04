"""Retain activation-time certification; historical receipts stay unknown."""
import sqlalchemy as sa
from alembic import op

revision = "hypermesh_0072_receipt_cert"
down_revision = "hypermesh_0071_fee_capture"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hypermesh_leases", sa.Column("host_certified_at_start", sa.Boolean(), nullable=True))
    op.execute("""CREATE FUNCTION hm_lease_certification_immutable() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
        IF (OLD.activated_at IS NOT NULL OR OLD.host_certified_at_start IS NOT NULL)
           AND NEW.host_certified_at_start IS DISTINCT FROM OLD.host_certified_at_start THEN
            RAISE EXCEPTION 'Activation certification receipt cannot change';
        END IF;
        RETURN NEW;
    END $$""")
    op.execute("""CREATE TRIGGER lease_certification_immutable
        BEFORE UPDATE ON hypermesh_leases
        FOR EACH ROW EXECUTE FUNCTION hm_lease_certification_immutable()""")


def downgrade():
    raise RuntimeError("Activation certification receipts must not be discarded")
