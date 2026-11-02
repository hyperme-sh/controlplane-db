"""Persist ciphertext state, shared floor, and independent store generations."""
from alembic import op
import sqlalchemy as sa

revision = "platform_0055_sociacl_keyring"
down_revision = "platform_0054_subject_scope"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sociacl_keyring_state",
        sa.Column("principal", sa.String(87), primary_key=True),
        sa.Column("head_floor", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("recovery_generation", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("wrap_generation", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("recovery", sa.LargeBinary(), nullable=False, server_default=sa.text("''::bytea")),
        sa.Column("wraps", sa.LargeBinary(), nullable=False, server_default=sa.text("''::bytea")),
        sa.CheckConstraint("principal ~ '^[A-Za-z0-9_-]{43}[.][A-Za-z0-9_-]{43}$'", name="ck_sociacl_keyring_principal"),
        sa.CheckConstraint("head_floor BETWEEN 0 AND 9007199254740991", name="ck_sociacl_keyring_floor"),
        sa.CheckConstraint("recovery_generation BETWEEN 0 AND 9007199254740991", name="ck_sociacl_recovery_generation"),
        sa.CheckConstraint("wrap_generation BETWEEN 0 AND 9007199254740991", name="ck_sociacl_wrap_generation"),
    )


def downgrade():
    # Exclude concurrent first writers before checking the downgrade precondition.
    op.execute("LOCK TABLE sociacl_keyring_state IN ACCESS EXCLUSIVE MODE")
    # Empty/deleted ciphertext still carries anti-replay state. Refuse to erase it.
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM sociacl_keyring_state) THEN
            RAISE EXCEPTION 'cannot discard SociACL floors or generations';
        END IF;
    END $$""")
    op.drop_table("sociacl_keyring_state")
