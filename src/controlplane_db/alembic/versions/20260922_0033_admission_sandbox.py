"""Admission sandbox soak + egress observation columns.

Revision ID: 0033_admission_sandbox
Revises: 0032_job_source_ref

Allow/promote requires an explicit lab soak pass and egress_ok=True.
Missing report fails closed. Certified still comes from the lab scorecard.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0033_admission_sandbox"
down_revision = "0032_job_source_ref"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE aiuditor_admissions "
            "ADD COLUMN IF NOT EXISTS sandbox_soak_ok BOOLEAN"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE aiuditor_admissions "
            "ADD COLUMN IF NOT EXISTS sandbox_egress_ok BOOLEAN"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE aiuditor_admissions "
            "ADD COLUMN IF NOT EXISTS sandbox_egress_reason VARCHAR(64)"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "ALTER TABLE aiuditor_admissions "
            "DROP COLUMN IF EXISTS sandbox_egress_reason"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE aiuditor_admissions DROP COLUMN IF EXISTS sandbox_egress_ok"
        )
    )
    op.execute(
        sa.text(
            "ALTER TABLE aiuditor_admissions DROP COLUMN IF EXISTS sandbox_soak_ok"
        )
    )
