"""Bind host certification and scorecards to software inventory."""
import sqlalchemy as sa
from alembic import op

revision = "hypermesh_0067_environment_cert"
down_revision = "hypermesh_0066_receipt_versions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hypermesh_jobs", sa.Column("result_effects_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hypermesh_devices", sa.Column("environment_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hypermesh_devices", sa.Column("observed_environment_hash", sa.String(71), nullable=True))
    op.add_column("hypermesh_devices", sa.Column("certified_environment_hash", sa.String(71), nullable=True))
    op.add_column("hypermesh_scorecards", sa.Column("certification_job_id", sa.Uuid(), nullable=True))
    op.add_column("hypermesh_jobs", sa.Column("environment_hash", sa.String(71), nullable=True))
    op.add_column("hypermesh_scorecards", sa.Column("environment_hash", sa.String(71), nullable=True))


def downgrade():
    raise RuntimeError("Certification environment provenance must not be discarded")
