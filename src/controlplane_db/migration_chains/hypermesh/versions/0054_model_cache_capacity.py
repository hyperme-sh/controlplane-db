"""Persist host-reported model cache admission capacity."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = "hypermesh_0054_cache_capacity"
down_revision = "hypermesh_0053_baseline"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("hypermesh_device_health", sa.Column("model_cache_hashes", JSONB(), nullable=True))
    op.add_column("hypermesh_jobs", sa.Column("file_hash", sa.String(256), nullable=True))
    op.add_column("hypermesh_jobs", sa.Column("size_bytes", sa.BigInteger(), nullable=True))
    op.alter_column("hypermesh_jobs", "source_ref", type_=sa.String(1024), existing_type=sa.String(512))
    op.add_column("hypermesh_device_health", sa.Column("model_cache_available_bytes", sa.BigInteger(), nullable=True))
    op.create_check_constraint("ck_hypermesh_health_cache_available", "hypermesh_device_health", "model_cache_available_bytes IS NULL OR model_cache_available_bytes >= 0")

def downgrade():
    # Keep source_ref widened: shrinking could truncate a retained source pin.
    op.drop_column("hypermesh_device_health", "model_cache_hashes")
    op.drop_column("hypermesh_jobs", "size_bytes")
    op.drop_column("hypermesh_jobs", "file_hash")
    op.drop_constraint("ck_hypermesh_health_cache_available", "hypermesh_device_health", type_="check")
    op.drop_column("hypermesh_device_health", "model_cache_available_bytes")
