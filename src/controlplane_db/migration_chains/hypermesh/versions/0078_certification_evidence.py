"""Retain server-owned compact certification verdict inputs on each job."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "hypermesh_0078_cert_evidence"
down_revision = "hypermesh_0077_saved_history"
branch_labels = None
depends_on = None


def upgrade():
    # Earlier measurements may already have been replaced. Never backfill a
    # historical job from the current device/catalog scorecard.
    op.add_column("hypermesh_jobs", sa.Column("certification_evidence", JSONB(none_as_null=True), nullable=True))


def downgrade():
    raise RuntimeError("Certification measurement provenance must not be discarded")
