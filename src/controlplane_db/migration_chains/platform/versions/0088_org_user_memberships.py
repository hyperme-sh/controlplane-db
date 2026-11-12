"""Tenant-consistent organization roles on existing directory users."""
from alembic import op

revision = 'platform_0088_org_memberships'
down_revision = 'platform_0087_first_contact'
branch_labels = None
depends_on = None


def upgrade():
    # The existing primary key already prevents duplicate id/tenant pairs.
    op.execute('ALTER TABLE users ADD CONSTRAINT uq_users_id_tenant UNIQUE (id, tenant_id)')
    op.execute('''
        CREATE TABLE organization_user_memberships (
            id uuid PRIMARY KEY,
            tenant_id uuid NOT NULL,
            organization_id uuid NOT NULL,
            user_id uuid NOT NULL,
            role varchar(16) NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT uq_org_user_membership_role UNIQUE (tenant_id, organization_id, user_id, role),
            CONSTRAINT fk_org_user_membership_org FOREIGN KEY (organization_id, tenant_id)
                REFERENCES organizations (id, tenant_id) ON DELETE CASCADE,
            CONSTRAINT fk_org_user_membership_user FOREIGN KEY (user_id, tenant_id)
                REFERENCES users (id, tenant_id) ON DELETE CASCADE,
            CONSTRAINT ck_org_user_membership_role CHECK (role IN ('member', 'owner', 'admin'))
        )
    ''')
    op.execute('ALTER TABLE organization_user_memberships ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE organization_user_memberships FORCE ROW LEVEL SECURITY')
    op.execute('''CREATE POLICY organization_membership_tenant ON organization_user_memberships
        USING (tenant_id::text = current_setting('app.current_tenant_id', true))
        WITH CHECK (tenant_id::text = current_setting('app.current_tenant_id', true))''')
    op.execute('REVOKE ALL ON organization_user_memberships FROM PUBLIC')


def downgrade():
    # Preserve real grants: populated tables need an explicit migration plan.
    op.execute('LOCK TABLE organization_user_memberships IN ACCESS EXCLUSIVE MODE')
    op.execute('SET LOCAL row_security = off')
    op.execute('''DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM organization_user_memberships) THEN
            RAISE EXCEPTION 'Organization membership downgrade requires an empty table';
        END IF;
    END $$''')
    op.execute('DROP TABLE organization_user_memberships')
    op.execute('ALTER TABLE users DROP CONSTRAINT uq_users_id_tenant')
