"""Immutable private model binding on existing paid P1 leases."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "hypermesh_0061_model_lease"
down_revision = "hypermesh_0061_validation_queue"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hypermesh_leases", sa.Column("private_model", JSONB(), nullable=True))
    op.execute("""CREATE FUNCTION hypermesh_private_lease_pin_immutable() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
        IF OLD.private_model IS NOT NULL AND (NEW.private_model IS NULL OR NEW.private_model != OLD.private_model) THEN
            RAISE EXCEPTION 'Private lease model pin is immutable';
        END IF;
        RETURN NEW;
    END $$""")
    op.execute("""CREATE TRIGGER hypermesh_private_lease_pin_immutable
        BEFORE UPDATE ON hypermesh_leases
        FOR EACH ROW EXECUTE FUNCTION hypermesh_private_lease_pin_immutable()""")


def downgrade():
    raise RuntimeError("Retain private lease bindings; disable placement for rollback")
