"""Erase deleted private-model targets without allowing lease retargeting."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "hypermesh_0079_model_erasure"
down_revision = "hypermesh_0078_account_admission"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "hypermesh_model_owner_erasures",
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("owner_sub", sa.String(512), primary_key=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("revisions", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("validations", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("lease_targets", sa.BigInteger(), nullable=False, server_default="0"),
        sa.CheckConstraint(
            "revisions >= 0 AND validations >= 0 AND lease_targets >= 0",
            name="ck_hm_owner_erasure_counts",
        ),
    )
    op.execute("ALTER TABLE hypermesh_model_owner_erasures ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE hypermesh_model_owner_erasures FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY tenant_isolation ON hypermesh_model_owner_erasures
        USING (tenant_id::text = nullif(current_setting('app.current_tenant_id', true), ''))
        WITH CHECK (tenant_id::text = nullif(current_setting('app.current_tenant_id', true), ''))""")
    # Destructive removal of only the original target is the sole exception.
    # No caller-selectable GUC, no new target/hash/validation ID, no live lease.
    # Check owner-recorded physical cleanup and closure under native row locks.
    op.execute("""CREATE OR REPLACE FUNCTION public.hypermesh_private_lease_pin_immutable()
    RETURNS trigger LANGUAGE plpgsql SET search_path=pg_catalog AS $$
    DECLARE cleanup_ack jsonb; record_created_at timestamptz;
    BEGIN
      IF OLD.private_model IS NOT NULL AND NEW.private_model IS DISTINCT FROM OLD.private_model THEN
        IF NEW.private_model IS NOT NULL
          AND OLD.private_model ? 'target'
          AND NEW.private_model = OLD.private_model - 'target'
          AND to_jsonb(NEW) - 'private_model' = to_jsonb(OLD) - 'private_model'
          AND OLD.status IN ('offered','ended','failed','refunded') THEN
          SELECT jsonb_path_query_first(r.lifecycle_audit,
            '$[*] ? (@.actor == "operations" && @.action == "deleted" && @.reason == "Exact version inventory has no live blobs")'), r.created_at
            INTO cleanup_ack, record_created_at
            FROM public.hypermesh_model_validations v
            JOIN public.hypermesh_model_revisions r ON r.id=v.revision_id AND r.tenant_id=v.tenant_id
            JOIN public.hypermesh_model_owner_closures c ON c.tenant_id=r.tenant_id AND c.owner_sub=r.owner_sub
            WHERE v.id=(OLD.private_model->>'validation_id')::uuid
              AND v.tenant_id=OLD.tenant_id AND v.target_sha256=OLD.private_model->>'target_sha256'
              AND v.owner_sub=r.owner_sub AND r.state='deleted' AND NOT r.retention_hold
              AND (r.retain_until IS NULL OR r.retain_until <= clock_timestamp())
              AND c.closed_at <= clock_timestamp() - interval '89 days'
              AND r.lifecycle_audit @> '[{"actor":"operations","action":"deleted","reason":"Exact version inventory has no live blobs"}]'::jsonb
              AND jsonb_typeof(r.lifecycle_audit)='array'
            FOR SHARE OF v,r,c;
          IF FOUND AND (cleanup_ack->>'at') ~ '(Z|[+-][0-9]{2}:[0-9]{2})$'
            AND (cleanup_ack->>'at')::timestamptz >= record_created_at
            AND (cleanup_ack->>'at')::timestamptz <= clock_timestamp()
          THEN RETURN NEW; END IF;
        END IF;
        RAISE EXCEPTION 'Private lease model pin is immutable';
      END IF;
      RETURN NEW;
    END $$""")


def downgrade():
    raise RuntimeError("Model target erasure is irreversible; retain erasure receipts")
