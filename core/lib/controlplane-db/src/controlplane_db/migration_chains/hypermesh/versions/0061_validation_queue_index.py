"""Index the live private lab queue alongside retained owner history."""

import sqlalchemy as sa
from alembic import op

revision = "hypermesh_0061_validation_queue"
down_revision = "hypermesh_0060_model_validation"
branch_labels = None
depends_on = None

def upgrade():
    op.create_index("ix_hm_validation_planned_device", "hypermesh_model_validations", ["tenant_id", "lab_device_id", "created_at", "expires_at"], postgresql_where=sa.text("state = 'planned'"))

def downgrade():
    op.drop_index("ix_hm_validation_planned_device", table_name="hypermesh_model_validations")
