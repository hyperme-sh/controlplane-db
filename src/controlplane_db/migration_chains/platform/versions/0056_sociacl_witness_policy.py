"""Retain the witness policy revision and permanent key lifecycle history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "platform_0056_witness_policy"
down_revision = "platform_0055_sociacl_keyring"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sociacl_witness_policy",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("revision", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("jwks", JSONB(), nullable=False, server_default=sa.text("'{\"keys\":[]}'::jsonb")),
        sa.Column("history", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("id = 1", name="ck_sociacl_policy_singleton"),
        sa.CheckConstraint("revision BETWEEN 0 AND 9007199254740991", name="ck_sociacl_policy_revision"),
    )


def downgrade():
    op.execute("LOCK TABLE sociacl_witness_policy IN ACCESS EXCLUSIVE MODE")
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM sociacl_witness_policy) THEN
            RAISE EXCEPTION 'cannot discard SociACL witness policy history';
        END IF;
    END $$""")
    op.drop_table("sociacl_witness_policy")
