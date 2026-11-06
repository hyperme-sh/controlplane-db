"""Separate renter-owned history and durable closure-retention tombstones."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
revision = "hypermesh_0077_saved_history"
down_revision = "hypermesh_0076_training_consent"
branch_labels = None
depends_on = None


def tenant():
    return sa.Column('tenant_id',UUID(as_uuid=True),sa.ForeignKey('tenants.id',ondelete='RESTRICT'),nullable=False)


def upgrade():
    op.create_table('hypermesh_history_preferences',tenant(),
        sa.Column('subject',sa.String(512),nullable=False),
        sa.Column('enabled',sa.Boolean(),nullable=False),sa.Column('generation',sa.Integer(),nullable=False),
        sa.Column('consent_at',sa.DateTime(timezone=True)),sa.Column('collect_after',sa.DateTime(timezone=True)),
        sa.Column('closed_at',sa.DateTime(timezone=True)),sa.Column('purged_at',sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint('tenant_id','subject'),sa.CheckConstraint('generation >= 0',name='ck_history_generation'),
        sa.CheckConstraint('(NOT enabled) OR (consent_at IS NOT NULL AND collect_after IS NOT NULL AND closed_at IS NULL)',name='ck_history_enabled'))
    op.create_index('ix_history_retention','hypermesh_history_preferences',['tenant_id','closed_at','subject'])
    op.create_table('hypermesh_history_entries',sa.Column('id',UUID(as_uuid=True),primary_key=True),tenant(),
        sa.Column('subject',sa.String(512),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('prompt',JSONB(),nullable=False),sa.Column('output',sa.LargeBinary(),nullable=False),
        sa.Column('media_type',sa.String(128),nullable=False))
    op.create_index('ix_history_owner','hypermesh_history_entries',['tenant_id','subject','created_at','id'])
    op.create_table('hypermesh_history_audit',sa.Column('id',UUID(as_uuid=True),primary_key=True),tenant(),
        sa.Column('subject',sa.String(512),nullable=False),sa.Column('actor',sa.String(512),nullable=False),
        sa.Column('action',sa.String(32),nullable=False),sa.Column('deleted_count',sa.Integer(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    for table in ('hypermesh_history_preferences','hypermesh_history_entries','hypermesh_history_audit'):
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f"""CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id::text = nullif(current_setting('app.current_tenant_id',true),''))
            WITH CHECK (tenant_id::text = nullif(current_setting('app.current_tenant_id',true),''))""")


def downgrade():
    raise RuntimeError('History consent, closure tombstones and deletion audits require retention review')
