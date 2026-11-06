"""Freeze original checkout terms and first verified capture identity."""
from alembic import op

revision = "hypermesh_0071_fee_capture"
down_revision = "hypermesh_0070_payout_terms"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE FUNCTION hm_processing_fee_immutable() RETURNS trigger
    LANGUAGE plpgsql AS $$ BEGIN
        IF OLD.processing_fee_binding IS NOT NULL AND (
            NEW.processing_fee_binding IS NULL OR
            (NEW.processing_fee_binding - 'capture') IS DISTINCT FROM (OLD.processing_fee_binding - 'capture') OR
            (OLD.processing_fee_binding ? 'capture' AND
             NEW.processing_fee_binding->'capture' IS DISTINCT FROM OLD.processing_fee_binding->'capture')
        ) THEN
            RAISE EXCEPTION 'Frozen processing fee terms cannot change';
        END IF;
        RETURN NEW;
    END $$""")
    op.execute("""CREATE TRIGGER processing_fee_immutable BEFORE UPDATE ON hypermesh_leases
        FOR EACH ROW EXECUTE FUNCTION hm_processing_fee_immutable()""")


def downgrade():
    raise RuntimeError("Original processing fee terms must remain protected")
