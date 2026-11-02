"""Scorecard host version and bench-import identity.

Revision ID: 0040_scorecard_host_version
Revises: 0039_lab_device_identity

``image_digest`` is already on hypermesh_scorecards. This revision has not
shipped. It adds the host software version the bench recorded, plus the
source repo, full commit, path, and file sha256. The same repo, commit, and
path, or the same file sha256, cannot be stored twice. Agent-posted
scorecards leave the source columns null.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0040_scorecard_host_version"
down_revision = "0039_lab_device_identity"
branch_labels = None
depends_on = None

_TABLE = "hypermesh_scorecards"


def upgrade() -> None:
    op.execute(
        sa.text(
            f"ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS host_version VARCHAR(128)"
        )
    )
    op.execute(
        sa.text(
            f"ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS source_repo VARCHAR(256)"
        )
    )
    op.execute(
        sa.text(
            f"ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS source_commit VARCHAR(64)"
        )
    )
    op.execute(
        sa.text(
            f"ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS source_path VARCHAR(512)"
        )
    )
    op.execute(
        sa.text(
            f"ALTER TABLE {_TABLE} ADD COLUMN IF NOT EXISTS content_sha256 VARCHAR(64)"
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_hm_scorecard_source
            ON {_TABLE} (source_repo, source_commit, source_path)
            WHERE source_repo IS NOT NULL
              AND source_commit IS NOT NULL
              AND source_path IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_hm_scorecard_content
            ON {_TABLE} (content_sha256)
            WHERE content_sha256 IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS uq_hm_scorecard_content"))
    op.execute(sa.text("DROP INDEX IF EXISTS uq_hm_scorecard_source"))
    for column in (
        "content_sha256",
        "source_path",
        "source_commit",
        "source_repo",
        "host_version",
    ):
        op.execute(sa.text(f"ALTER TABLE {_TABLE} DROP COLUMN IF EXISTS {column}"))
