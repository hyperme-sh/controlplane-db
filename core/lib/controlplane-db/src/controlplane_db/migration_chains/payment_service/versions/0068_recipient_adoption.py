"""Immutable sandbox adoption reservation and first binding observation."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "payment_service_0068_adoption"
down_revision = "payment_service_0067_controls"
branch_labels = None
depends_on = None

ORIGINAL = """CREATE OR REPLACE FUNCTION public.connect_recipient_progress_only() RETURNS trigger
PROGRESS = """CREATE OR REPLACE FUNCTION public.connect_recipient_progress_only() RETURNS trigger
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
    END $$;"""    BEGIN
      IF (to_jsonb(NEW) - 'stripe_account_id' - 'creation_status' - 'capability_status' - 'capability_observed_at') IS DISTINCT FROM
         (to_jsonb(OLD) - 'stripe_account_id' - 'creation_status' - 'capability_status' - 'capability_observed_at') OR
         (OLD.stripe_account_id IS NOT NULL AND NEW.stripe_account_id IS DISTINCT FROM (OLD.stripe_account_id)) OR
         (OLD.creation_status = 'reconciliation_required' AND NEW.creation_status = 'pending_creation') OR
         (OLD.capability_observed_at IS NOT NULL AND
           (NEW.capability_observed_at IS NULL OR NEW.capability_observed_at < OLD.capability_observed_at OR
            (NEW.capability_status IS DISTINCT FROM (OLD.capability_status) AND NEW.capability_observed_at <= OLD.capability_observed_at))) THEN
        RAISE EXCEPTION 'Connect recipient history cannot be rewritten' USING ERRCODE = '23514';
      END IF;
      RETURN NEW;
    END $$;"""
PROGRESS = "CREATE OR REPLACE FUNCTION public.connect_recipient_progress_only() RETURNS trigger\nLANGUAGE plpgsql SET search_path = pg_catalog AS $$\n    BEGIN\n      IF (to_jsonb(NEW) - 'stripe_account_id' - 'creation_status' - 'capability_status' - 'capability_observed_at' - 'adoption_result') IS DISTINCT FROM\n         (to_jsonb(OLD) - 'stripe_account_id' - 'creation_status' - 'capability_status' - 'capability_observed_at' - 'adoption_result') OR\n         (OLD.adoption_result IS NOT NULL AND NEW.adoption_result IS DISTINCT FROM OLD.adoption_result) OR\n         (OLD.stripe_account_id IS NOT NULL AND NEW.stripe_account_id IS DISTINCT FROM (OLD.stripe_account_id)) OR\n         (OLD.creation_status = 'reconciliation_required' AND NEW.creation_status = 'pending_creation') OR\n         (OLD.capability_observed_at IS NOT NULL AND\n           (NEW.capability_observed_at IS NULL OR NEW.capability_observed_at < OLD.capability_observed_at OR\n            (NEW.capability_status IS DISTINCT FROM (OLD.capability_status) AND NEW.capability_observed_at <= OLD.capability_observed_at))) THEN\n        RAISE EXCEPTION 'Connect recipient history cannot be rewritten' USING ERRCODE = '23514';\n      END IF;\n      RETURN NEW;\n    END $$;"


def upgrade():
    op.add_column(
        "connect_recipient_accounts",
        sa.Column("adoption", JSONB(none_as_null=True), nullable=True),
    )
    op.add_column(
        "connect_recipient_accounts",
        sa.Column("adoption_result", JSONB(none_as_null=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_recipient_adoption_plan",
        "connect_recipient_accounts",
        "adoption IS NULL OR (jsonb_typeof(adoption) = 'object' AND adoption ?& ARRAY['account_id','owner_sub','mapping','ownership','original'] AND jsonb_typeof(adoption->'account_id') = 'string' AND jsonb_typeof(adoption->'owner_sub') = 'string' AND jsonb_typeof(adoption->'mapping') = 'object' AND jsonb_typeof(adoption->'ownership') = 'object' AND jsonb_typeof(adoption->'original') = 'object' AND adoption->>'account_id' ~ '^acct_[A-Za-z0-9]+$' AND length(adoption->>'owner_sub') BETWEEN 1 AND 512)",
    )
    op.create_check_constraint(
        "ck_recipient_adoption_binding",
        "connect_recipient_accounts",
        "adoption IS NULL OR stripe_account_id IS NULL OR stripe_account_id = adoption->>'account_id'",
    )
    op.create_check_constraint(
        "ck_recipient_adoption_result",
        "connect_recipient_accounts",
        "adoption_result IS NULL OR (adoption IS NOT NULL AND stripe_account_id IS NOT NULL AND creation_status = 'bound' AND jsonb_typeof(adoption_result) = 'object')",
    )
    op.create_index(
        "uq_recipient_reserved_account",
        "connect_recipient_accounts",
        [sa.text("COALESCE(stripe_account_id, adoption->>'account_id')")],
        unique=True,
    )
    op.execute(PROGRESS)


def downgrade():
    op.execute("SET LOCAL row_security = off")
    op.execute("LOCK TABLE public.connect_recipient_accounts IN ACCESS EXCLUSIVE MODE")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM public.connect_recipient_accounts WHERE adoption IS NOT NULL OR adoption_result IS NOT NULL) THEN RAISE EXCEPTION 'Cannot remove nonempty adoption history'; END IF; END $$;"
    )
    op.execute(ORIGINAL)
    op.drop_index(
        "uq_recipient_reserved_account", table_name="connect_recipient_accounts"
    )
    for name in (
        "ck_recipient_adoption_result",
        "ck_recipient_adoption_binding",
        "ck_recipient_adoption_plan",
    ):
        op.drop_constraint(name, "connect_recipient_accounts", type_="check")
    op.drop_column("connect_recipient_accounts", "adoption_result")
    op.drop_column("connect_recipient_accounts", "adoption")
