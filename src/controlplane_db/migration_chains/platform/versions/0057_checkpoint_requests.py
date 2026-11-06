"""Keep permanent checkpoint challenge consumption records."""
from alembic import op
import sqlalchemy as sa

revision = 'platform_0057_checkpoint_replay'
down_revision = 'platform_0056_witness_policy'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('sociacl_checkpoint_requests',
        sa.Column('request_hash', sa.String(64), primary_key=True),
        sa.Column('consumed_at', sa.BigInteger(), nullable=False),
        sa.CheckConstraint("request_hash ~ '^[0-9a-f]{64}$'", name='ck_checkpoint_request_hash'),
        sa.CheckConstraint('consumed_at BETWEEN 0 AND 9007199254740991', name='ck_checkpoint_consumed_at'))


def downgrade():
    op.execute('LOCK TABLE sociacl_checkpoint_requests IN ACCESS EXCLUSIVE MODE')
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM sociacl_checkpoint_requests) THEN
            RAISE EXCEPTION 'cannot discard checkpoint replay history';
        END IF;
    END $$""")
    op.drop_table('sociacl_checkpoint_requests')
