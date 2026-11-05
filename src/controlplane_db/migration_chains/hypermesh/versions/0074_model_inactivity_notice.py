"""Private model inactivity notices and activation history."""
from alembic import op
import sqlalchemy as sa

revision = "hypermesh_0074_model_inactivity"
down_revision = "hypermesh_0073_self_use"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("hypermesh_model_revisions", sa.Column("inactivity_anchor_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hypermesh_model_revisions", sa.Column("inactivity_notice_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("hypermesh_model_revisions", sa.Column("inactivity_delete_after", sa.DateTime(timezone=True), nullable=True))
    op.execute("""CREATE INDEX ix_hm_private_activation ON hypermesh_leases
        (tenant_id, (private_model ->> 'validation_id'), activated_at)
        WHERE private_model IS NOT NULL AND activated_at IS NOT NULL""")


def downgrade():
    raise RuntimeError("Published model inactivity notices must not be discarded")
