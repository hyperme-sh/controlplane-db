"""Retain recipient contact before provider creation, without changing old bindings."""

import sqlalchemy as sa
from alembic import op

revision = "payment_service_0072_contact"
down_revision = "payment_service_0071_bank_access"
branch_labels = None
depends_on = None
ORIGINAL = """CREATE OR REPLACE FUNCTION public.connect_recipient_progress_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    BEGIN
      IF (to_jsonb(NEW) - 'stripe_account_id' - 'creation_status' - 'capability_status' - 'capability_observed_at' - 'adoption_result') IS DISTINCT FROM
         (to_jsonb(OLD) - 'stripe_account_id' - 'creation_status' - 'capability_status' - 'capability_observed_at' - 'adoption_result') OR
         (OLD.adoption_result IS NOT NULL AND NEW.adoption_result IS DISTINCT FROM OLD.adoption_result) OR
         (OLD.stripe_account_id IS NOT NULL AND NEW.stripe_account_id IS DISTINCT FROM (OLD.stripe_account_id)) OR
         (OLD.creation_status = 'reconciliation_required' AND NEW.creation_status = 'pending_creation') OR
         (OLD.capability_observed_at IS NOT NULL AND
           (NEW.capability_observed_at IS NULL OR NEW.capability_observed_at < OLD.capability_observed_at OR
            (NEW.capability_status IS DISTINCT FROM (OLD.capability_status) AND NEW.capability_observed_at <= OLD.capability_observed_at))) THEN
        RAISE EXCEPTION 'Connect recipient history cannot be rewritten' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$;"""
PROGRESS = """CREATE OR REPLACE FUNCTION public.connect_recipient_progress_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    BEGIN
      IF (to_jsonb(NEW) - 'stripe_account_id' - 'creation_status' - 'capability_status' - 'capability_observed_at' - 'adoption_result' - 'contact_email') IS DISTINCT FROM
         (to_jsonb(OLD) - 'stripe_account_id' - 'creation_status' - 'capability_status' - 'capability_observed_at' - 'adoption_result' - 'contact_email') OR
         (NEW.contact_email IS DISTINCT FROM OLD.contact_email AND (OLD.contact_email IS NOT NULL OR OLD.stripe_account_id IS NOT NULL OR OLD.creation_status <> 'pending_creation' OR NEW.contact_email IS NULL)) OR
         (OLD.adoption_result IS NOT NULL AND NEW.adoption_result IS DISTINCT FROM OLD.adoption_result) OR
         (OLD.stripe_account_id IS NOT NULL AND NEW.stripe_account_id IS DISTINCT FROM (OLD.stripe_account_id)) OR
         (OLD.creation_status = 'reconciliation_required' AND NEW.creation_status = 'pending_creation') OR
         (OLD.capability_observed_at IS NOT NULL AND
           (NEW.capability_observed_at IS NULL OR NEW.capability_observed_at < OLD.capability_observed_at OR
            (NEW.capability_status IS DISTINCT FROM (OLD.capability_status) AND NEW.capability_observed_at <= OLD.capability_observed_at))) THEN
        RAISE EXCEPTION 'Connect recipient history cannot be rewritten' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$;"""


def upgrade():
    op.add_column(
        "connect_recipient_accounts",
        sa.Column("contact_email", sa.String(254), nullable=True),
    )
    op.execute(PROGRESS)


def downgrade():
    op.execute("LOCK TABLE public.connect_recipient_accounts IN ACCESS EXCLUSIVE MODE")
    op.execute("SET LOCAL row_security = off")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM public.connect_recipient_accounts WHERE contact_email IS NOT NULL) THEN
        RAISE EXCEPTION 'Cannot remove recipient contact history' USING ERRCODE = '23514';
      END IF;
    END $$;""")
    op.execute(ORIGINAL)
    op.drop_column("connect_recipient_accounts", "contact_email")
