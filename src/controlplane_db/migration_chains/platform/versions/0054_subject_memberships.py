"""Scope user identity uniqueness to platform or tenant membership."""
from alembic import op

revision = "platform_0054_subject_scope"
down_revision = "platform_0053_baseline"
branch_labels = None
depends_on = None


def upgrade():
    # Build the narrower constraints before removing the global one. Existing
    # rows and their subject bindings are preserved, including deleted accounts.
    op.execute("""CREATE UNIQUE INDEX uq_users_tenant_keycloak_sub
        ON users (tenant_id, keycloak_sub)
        WHERE tenant_id IS NOT NULL AND keycloak_sub IS NOT NULL""")
    op.execute("""CREATE UNIQUE INDEX uq_users_platform_keycloak_sub
        ON users (keycloak_sub)
        WHERE tenant_id IS NULL AND keycloak_sub IS NOT NULL""")
    op.drop_index("ix_users_keycloak_sub_unique", table_name="users")


def downgrade():
    # Fail transactionally if identities now have multiple memberships.
    # Never discard a membership or erase its subject to permit a downgrade.
    op.execute("""CREATE UNIQUE INDEX ix_users_keycloak_sub_unique
        ON users (keycloak_sub) WHERE keycloak_sub IS NOT NULL""")
    op.drop_index("uq_users_platform_keycloak_sub", table_name="users")
    op.drop_index("uq_users_tenant_keycloak_sub", table_name="users")
