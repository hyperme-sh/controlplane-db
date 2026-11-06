"""Lease-owner violation replay receipts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
revision = "hypermesh_0070_violation_ops"
down_revision = 'hypermesh_0069_lab_binding'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('hypermesh_violation_operations',
        sa.Column('tenant_id', UUID(as_uuid=True), sa.ForeignKey('tenants.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('operation_id', UUID(as_uuid=True), primary_key=True),
        sa.Column('lease_id', UUID(as_uuid=True), nullable=False),
        sa.Column('binding', sa.Text(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True))
    op.execute('ALTER TABLE hypermesh_violation_operations ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE hypermesh_violation_operations FORCE ROW LEVEL SECURITY')
    op.execute("""CREATE POLICY tenant_isolation ON hypermesh_violation_operations
        USING (tenant_id::text = nullif(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id::text = nullif(current_setting('app.current_tenant_id', true), ''))""")

def downgrade():
    raise RuntimeError('Retain replay receipts; roll back callers instead')
