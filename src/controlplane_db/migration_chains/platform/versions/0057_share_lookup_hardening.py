"""Pin share lookup resolution and restrict public execution."""
from alembic import op
from controlplane_db._share_lookup_hardening import apply

revision = 'platform_0057_share_lookup'
down_revision = 'platform_0056_witness_policy'
branch_labels = None
depends_on = None


def upgrade():
    apply(op.get_bind())


def downgrade():
    # Keep the hardened function when rolling back application images.
    pass
