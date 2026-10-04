"""initial schema + RLS policies

Revision ID: 0001
Revises:
Create Date: 2025-03-30

"""

from typing import Sequence, Union

from alembic import op

from controlplane_db.alembic.legacy_models import Base

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TENANT_TABLES = (
    "users",
    "roles",
    "user_password_resets",
    "user_preferences",
    "storage_settings",
    "chat_histories_ai",
    "chat_sessions_ai",
    "user_passkeys",
    "user_passkey_challenges",
    "user_magic_links",
    "stripe_settings",
    "billing_records",
    "subscription_plans",
    "notification_banner_settings",
    "sso_settings",
    "branding_configuration",
)


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

    # RLS: tenant-scoped rows match app.current_tenant_id; platform rows (tenant_id IS NULL) when setting is empty.
    for table in _TENANT_TABLES:
        op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_select ON "{table}"
            FOR SELECT
            USING (
                (current_setting('app.current_tenant_id', true) = '' AND tenant_id IS NULL)
                OR (
                    current_setting('app.current_tenant_id', true) <> ''
                    AND tenant_id IS NOT NULL
                    AND tenant_id = current_setting('app.current_tenant_id', true)::uuid
                )
            )
            """
        )
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_insert ON "{table}"
            FOR INSERT
            WITH CHECK (
                (current_setting('app.current_tenant_id', true) = '' AND tenant_id IS NULL)
                OR (
                    current_setting('app.current_tenant_id', true) <> ''
                    AND tenant_id IS NOT NULL
                    AND tenant_id = current_setting('app.current_tenant_id', true)::uuid
                )
            )
            """
        )
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_update ON "{table}"
            FOR UPDATE
            USING (
                (current_setting('app.current_tenant_id', true) = '' AND tenant_id IS NULL)
                OR (
                    current_setting('app.current_tenant_id', true) <> ''
                    AND tenant_id IS NOT NULL
                    AND tenant_id = current_setting('app.current_tenant_id', true)::uuid
                )
            )
            WITH CHECK (
                (current_setting('app.current_tenant_id', true) = '' AND tenant_id IS NULL)
                OR (
                    current_setting('app.current_tenant_id', true) <> ''
                    AND tenant_id IS NOT NULL
                    AND tenant_id = current_setting('app.current_tenant_id', true)::uuid
                )
            )
            """
        )
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_delete ON "{table}"
            FOR DELETE
            USING (
                (current_setting('app.current_tenant_id', true) = '' AND tenant_id IS NULL)
                OR (
                    current_setting('app.current_tenant_id', true) <> ''
                    AND tenant_id IS NOT NULL
                    AND tenant_id = current_setting('app.current_tenant_id', true)::uuid
                )
            )
            """
        )


def downgrade() -> None:
    for table in _TENANT_TABLES:
        for pol in (
            "tenant_isolation_select",
            "tenant_isolation_insert",
            "tenant_isolation_update",
            "tenant_isolation_delete",
        ):
            op.execute(f'DROP POLICY IF EXISTS {pol} ON "{table}"')
        op.execute(f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY')
    bind = op.get_bind()
    Base.metadata.drop_all(bind=bind)
