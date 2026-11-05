"""Explicit per-account training consent and separately owned submissions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
revision = "hypermesh_0076_training_consent"
down_revision = "hypermesh_0075_model_closure"
branch_labels = None
depends_on = None


def tenant():
    return sa.Column('tenant_id',UUID(as_uuid=True),sa.ForeignKey('tenants.id',ondelete='RESTRICT'),nullable=False)


def upgrade():
    op.create_table('hypermesh_training_consents',tenant(),
        sa.Column('subject',sa.String(512),nullable=False),
        sa.Column('enabled',sa.Boolean(),nullable=False),
        sa.Column('generation',sa.Integer(),nullable=False),
        sa.Column('consent_at',sa.DateTime(timezone=True)),
        sa.Column('collect_after',sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint('tenant_id','subject'),
        sa.CheckConstraint('generation >= 0',name='ck_training_generation'),
        sa.CheckConstraint('(enabled AND consent_at IS NOT NULL AND collect_after IS NOT NULL) OR (NOT enabled AND consent_at IS NULL)',name='ck_training_consent_time'))
    op.create_table('hypermesh_training_submissions',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),tenant(),
        sa.Column('subject',sa.String(512),nullable=False),
        sa.Column('consent_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('prompt',JSONB(),nullable=False),sa.Column('output',sa.LargeBinary(),nullable=False),
        sa.Column('media_type',sa.String(128),nullable=False))
    op.create_index('ix_training_account','hypermesh_training_submissions',['tenant_id','subject'])
    op.create_table('hypermesh_training_deletions',
        sa.Column('id',UUID(as_uuid=True),primary_key=True),tenant(),
        sa.Column('subject',sa.String(512),nullable=False),sa.Column('actor',sa.String(512),nullable=False),
        sa.Column('deleted_count',sa.Integer(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    for table in ('hypermesh_training_consents','hypermesh_training_submissions','hypermesh_training_deletions'):
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f"""CREATE POLICY tenant_isolation ON {table}
            USING (tenant_id::text = nullif(current_setting('app.current_tenant_id',true),''))
            WITH CHECK (tenant_id::text = nullif(current_setting('app.current_tenant_id',true),''))""")


def downgrade():
    raise RuntimeError('Training consent, submissions and deletion audit require explicit retention review')
