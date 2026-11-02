"""Reserved historical revision; physical host inventory is enrollment-owned.

Previously promoted a particular box. Fresh databases must not encode physical
device identities. Existing records remain available for owner retirement.
"""
revision = "0039_lab_device_identity"
down_revision = "0038_aiuditor_size_bytes_bigint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
