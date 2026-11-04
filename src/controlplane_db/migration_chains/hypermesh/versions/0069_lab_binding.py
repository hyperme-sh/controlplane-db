"""Freeze lab assignment pins before measuring an artifact."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = "hypermesh_0069_lab_binding"
down_revision = "hypermesh_0068_environment_cert"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("hypermesh_jobs", sa.Column("lab_binding", JSONB, nullable=True))

def downgrade():
    raise RuntimeError("Retain immutable lab bindings; disable publication for rollback")
