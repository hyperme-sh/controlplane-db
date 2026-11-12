"""Public first-contact ciphertext, isolated from accepted private lanes."""
from alembic import op

revision = "platform_0087_first_contact"
down_revision = "platform_0086_contact_lanes"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE sociacl_first_contact_messages (
            lane_id text NOT NULL CHECK (lane_id ~ '^[0-9a-f]{64}$'),
            message_id text NOT NULL CHECK (message_id ~ '^[0-9a-f]{64}$'),
            ciphertext bytea NOT NULL CHECK (octet_length(ciphertext) BETWEEN 94 AND 8192),
            byte_size integer GENERATED ALWAYS AS (octet_length(ciphertext)) STORED,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            expires_at timestamptz NOT NULL,
            PRIMARY KEY (lane_id, message_id),
            CHECK (expires_at > created_at AND expires_at <= created_at + interval '7 days')
        )
    """)
    op.execute("CREATE INDEX sociacl_first_contact_expiry ON sociacl_first_contact_messages (expires_at)")
    op.execute("REVOKE ALL ON sociacl_first_contact_messages FROM PUBLIC")


def downgrade():
    op.execute("DROP TABLE sociacl_first_contact_messages")
