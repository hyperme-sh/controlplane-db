"""Durable owner access lifecycle; no financial or grant journal rewrites."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "payment_service_0070_lifecycle"
down_revision = "payment_service_0069_access"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "connect_access_states",
        sa.Column(
            "lifecycle", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    op.create_check_constraint(
        "ck_access_lifecycle",
        "connect_access_states",
        "jsonb_typeof(lifecycle) = 'object'",
    )


def downgrade():
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM connect_access_states WHERE lifecycle <> '{}'::jsonb) THEN
        RAISE EXCEPTION 'Cannot remove access lifecycle history' USING ERRCODE = '23514';
      END IF;
    END $$""")
    op.drop_constraint("ck_access_lifecycle", "connect_access_states")
    op.drop_column("connect_access_states", "lifecycle")
