"""Native financial-source invalidation and server-owned retention clocks."""

import sqlalchemy as sa
from alembic import op

revision = "payment_service_0076_financial"
down_revision = "payment_service_0075_exposure"
branch_labels = None
depends_on = None

CLOCK_TABLES = (
    "host_payout_addresses",
    "connect_recipient_accounts",
    "billing_tax_orders",
    "billing_tax_calculations",
    "connect_bank_approvals",
    "connect_reversal_exposure_observations",
    "connect_control_proofs",
)
SOURCE_TABLES = (
    "host_payout_addresses",
    "connect_recipient_accounts",
    "billing_tax_orders",
    "billing_tax_calculations",
    "connect_bank_approvals",
    "connect_reversal_exposure_observations",
    "connect_control_proofs",
    "connect_access_states",
    "connect_access_grants",
    "connect_access_results",
    "payer_mismatch_accounts",
)
ORIGINAL_PROGRESS = """CREATE OR REPLACE FUNCTION public.connect_recipient_progress_only() RETURNS trigger
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
PROGRESS = """CREATE OR REPLACE FUNCTION public.connect_recipient_progress_only() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$
    BEGIN
      IF (to_jsonb(NEW) - 'financial_activity_at' - 'financial_retain_until' - 'stripe_account_id' - 'creation_status' - 'capability_status' - 'capability_observed_at' - 'adoption_result' - 'contact_email') IS DISTINCT FROM
         (to_jsonb(OLD) - 'financial_activity_at' - 'financial_retain_until' - 'stripe_account_id' - 'creation_status' - 'capability_status' - 'capability_observed_at' - 'adoption_result' - 'contact_email') OR
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
    op.execute("SELECT public.account_lock_financial_fence_changes()")
    op.execute("SET LOCAL row_security=off")
    op.add_column(
        "connect_recipient_accounts",
        sa.Column("initiated_by_sub", sa.String(512), nullable=True),
    )
    op.create_check_constraint(
        "ck_recipient_initiator",
        "connect_recipient_accounts",
        "initiated_by_sub IS NULL OR (length(btrim(initiated_by_sub)) BETWEEN 1 AND 512 AND initiated_by_sub NOT LIKE 'apikey:%')",
    )
    op.add_column(
        "host_payout_addresses",
        sa.Column("financial_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "host_payout_addresses",
        sa.Column("financial_retain_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_host_payout_addresses_financial_clock",
        "host_payout_addresses",
        "(financial_activity_at IS NULL AND financial_retain_until IS NULL) OR (financial_activity_at IS NOT NULL AND financial_retain_until IS NOT NULL AND financial_retain_until > financial_activity_at)",
    )
    op.create_index(
        "ix_host_payout_addresses_financial_due",
        "host_payout_addresses",
        ["financial_retain_until"],
    )
    op.add_column(
        "connect_recipient_accounts",
        sa.Column("financial_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "connect_recipient_accounts",
        sa.Column("financial_retain_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_connect_recipient_accounts_financial_clock",
        "connect_recipient_accounts",
        "(financial_activity_at IS NULL AND financial_retain_until IS NULL) OR (financial_activity_at IS NOT NULL AND financial_retain_until IS NOT NULL AND financial_retain_until > financial_activity_at)",
    )
    op.create_index(
        "ix_connect_recipient_accounts_financial_due",
        "connect_recipient_accounts",
        ["financial_retain_until"],
    )
    op.add_column(
        "billing_tax_orders",
        sa.Column("financial_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "billing_tax_orders",
        sa.Column("financial_retain_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_billing_tax_orders_financial_clock",
        "billing_tax_orders",
        "(financial_activity_at IS NULL AND financial_retain_until IS NULL) OR (financial_activity_at IS NOT NULL AND financial_retain_until IS NOT NULL AND financial_retain_until > financial_activity_at)",
    )
    op.create_index(
        "ix_billing_tax_orders_financial_due",
        "billing_tax_orders",
        ["financial_retain_until"],
    )
    op.add_column(
        "billing_tax_calculations",
        sa.Column("financial_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "billing_tax_calculations",
        sa.Column("financial_retain_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_billing_tax_calculations_financial_clock",
        "billing_tax_calculations",
        "(financial_activity_at IS NULL AND financial_retain_until IS NULL) OR (financial_activity_at IS NOT NULL AND financial_retain_until IS NOT NULL AND financial_retain_until > financial_activity_at)",
    )
    op.create_index(
        "ix_billing_tax_calculations_financial_due",
        "billing_tax_calculations",
        ["financial_retain_until"],
    )
    op.add_column(
        "connect_bank_approvals",
        sa.Column("financial_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "connect_bank_approvals",
        sa.Column("financial_retain_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_connect_bank_approvals_financial_clock",
        "connect_bank_approvals",
        "(financial_activity_at IS NULL AND financial_retain_until IS NULL) OR (financial_activity_at IS NOT NULL AND financial_retain_until IS NOT NULL AND financial_retain_until > financial_activity_at)",
    )
    op.create_index(
        "ix_connect_bank_approvals_financial_due",
        "connect_bank_approvals",
        ["financial_retain_until"],
    )
    op.add_column(
        "connect_reversal_exposure_observations",
        sa.Column("financial_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "connect_reversal_exposure_observations",
        sa.Column("financial_retain_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_connect_reversal_exposure_observations_financial_clock",
        "connect_reversal_exposure_observations",
        "(financial_activity_at IS NULL AND financial_retain_until IS NULL) OR (financial_activity_at IS NOT NULL AND financial_retain_until IS NOT NULL AND financial_retain_until > financial_activity_at)",
    )
    op.create_index(
        "ix_connect_reversal_exposure_observations_financial_due",
        "connect_reversal_exposure_observations",
        ["financial_retain_until"],
    )
    op.add_column(
        "connect_control_proofs",
        sa.Column("financial_activity_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "connect_control_proofs",
        sa.Column("financial_retain_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_connect_control_proofs_financial_clock",
        "connect_control_proofs",
        "(financial_activity_at IS NULL AND financial_retain_until IS NULL) OR (financial_activity_at IS NOT NULL AND financial_retain_until IS NOT NULL AND financial_retain_until > financial_activity_at)",
    )
    op.create_index(
        "ix_connect_control_proofs_financial_due",
        "connect_control_proofs",
        ["financial_retain_until"],
    )
    # ADD COLUMN holds ACCESS EXCLUSIVE locks through this migration transaction.
    # Remove only the five UPDATE guards for this historical clock backfill;
    # DELETE/TRUNCATE guards stay installed. Restore every guard before commit.
    op.execute("DROP TRIGGER control_proof_update ON public.connect_control_proofs")
    op.execute(
        "DROP TRIGGER connect_bank_approvals_update ON public.connect_bank_approvals"
    )
    op.execute(
        "DROP TRIGGER reversal_exposure_update ON public.connect_reversal_exposure_observations"
    )
    op.execute("DROP TRIGGER tax_order_update ON public.billing_tax_orders")
    op.execute(
        "DROP TRIGGER tax_calculation_progress ON public.billing_tax_calculations"
    )
    op.execute(PROGRESS)
    backfill_tables = (
        "host_payout_addresses", "connect_bank_approvals",
        "connect_reversal_exposure_observations", "connect_control_proofs",
        "connect_recipient_accounts", "billing_tax_orders", "billing_tax_calculations",
    )
    for table in backfill_tables:
        op.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
    # Historical timestamps remain their own anchor, never rollout/closure time.
    # An unobserved legacy recipient binding has no trustworthy final timestamp.
    # Keep that clock unknown; erasure must require reconciliation, not guess it.
    op.execute(
        "UPDATE host_payout_addresses SET financial_activity_at=verified_at, financial_retain_until=(((verified_at) AT TIME ZONE 'UTC')+interval '7 years') AT TIME ZONE 'UTC'"
    )
    op.execute(
        "UPDATE connect_bank_approvals SET financial_activity_at=approved_at, financial_retain_until=(((approved_at) AT TIME ZONE 'UTC')+interval '7 years') AT TIME ZONE 'UTC'"
    )
    op.execute(
        "UPDATE connect_reversal_exposure_observations SET financial_activity_at=recorded_at, financial_retain_until=(((recorded_at) AT TIME ZONE 'UTC')+interval '7 years') AT TIME ZONE 'UTC'"
    )
    op.execute(
        "UPDATE connect_control_proofs SET financial_activity_at=accepted_at, financial_retain_until=(((accepted_at) AT TIME ZONE 'UTC')+interval '7 years') AT TIME ZONE 'UTC'"
    )
    op.execute("""UPDATE connect_recipient_accounts SET
      financial_activity_at=greatest(created_at,attempted_at,capability_observed_at),
      financial_retain_until=((greatest(created_at,attempted_at,capability_observed_at) AT TIME ZONE 'UTC')+interval '7 years') AT TIME ZONE 'UTC'
      WHERE capability_observed_at IS NOT NULL""")
    # Tax timestamps are conservatively at least the authoritative payment's
    # last activity. The curated platform projection retains platform ownership.
    op.execute("""UPDATE billing_tax_orders o SET
      financial_activity_at=greatest(o.created_at,(public.account_billing_financial_source(o.billing_record_id,o.tenant_id)->>'financial_activity_at')::timestamptz),
      financial_retain_until=((greatest(o.created_at,(public.account_billing_financial_source(o.billing_record_id,o.tenant_id)->>'financial_activity_at')::timestamptz) AT TIME ZONE 'UTC')+interval '7 years') AT TIME ZONE 'UTC'
      WHERE (public.account_billing_financial_source(o.billing_record_id,o.tenant_id)->>'financial_activity_at') IS NOT NULL""")
    op.execute("""UPDATE billing_tax_calculations c SET financial_activity_at=greatest(c.attempted_at,o.financial_activity_at),
      financial_retain_until=((greatest(c.attempted_at,o.financial_activity_at) AT TIME ZONE 'UTC')+interval '7 years') AT TIME ZONE 'UTC'
      FROM billing_tax_orders o WHERE o.revision_id=c.revision_id AND o.tenant_id=c.tenant_id AND o.financial_activity_at IS NOT NULL""")
    for table in backfill_tables:
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE TRIGGER connect_bank_approvals_update BEFORE UPDATE ON public.connect_bank_approvals FOR EACH ROW EXECUTE FUNCTION public.connect_recipient_immutable()"
    )
    op.execute(
        "CREATE TRIGGER reversal_exposure_update BEFORE UPDATE ON public.connect_reversal_exposure_observations FOR EACH ROW EXECUTE FUNCTION public.connect_recipient_immutable()"
    )
    op.execute(
        "CREATE TRIGGER tax_order_update BEFORE UPDATE ON public.billing_tax_orders FOR EACH ROW EXECUTE FUNCTION public.tax_history_retained()"
    )
    op.execute(
        "CREATE TRIGGER tax_calculation_progress BEFORE INSERT OR UPDATE ON public.billing_tax_calculations FOR EACH ROW EXECUTE FUNCTION public.tax_calculation_progress()"
    )
    op.execute(
        "CREATE TRIGGER control_proof_update BEFORE UPDATE ON public.connect_control_proofs FOR EACH ROW EXECUTE FUNCTION public.control_proof_once()"
    )
    op.execute("""CREATE OR REPLACE FUNCTION public.control_proof_once() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
      IF OLD.report IS NOT NULL OR NEW.report IS NULL OR NEW.accepted_at IS NULL OR
        (to_jsonb(NEW)-ARRAY['report','accepted_at','financial_activity_at','financial_retain_until'])
          IS DISTINCT FROM
        (to_jsonb(OLD)-ARRAY['report','accepted_at','financial_activity_at','financial_retain_until']) THEN
        RAISE EXCEPTION 'Host-control proof history is immutable' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute("""CREATE FUNCTION public.payment_financial_clock()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
    DECLARE significant boolean;
    BEGIN
      IF TG_OP='INSERT' THEN
        IF NEW.financial_activity_at IS NOT NULL OR NEW.financial_retain_until IS NOT NULL THEN
          RAISE EXCEPTION 'Native financial clocks are server recorded' USING ERRCODE='42501';
        END IF;
        NEW.financial_activity_at := clock_timestamp();
        IF TG_TABLE_NAME='connect_control_proofs' AND (to_jsonb(NEW)->>'accepted_at') IS NULL THEN
          NEW.financial_activity_at := NULL;
        END IF;
      ELSE
        IF NEW.financial_activity_at IS DISTINCT FROM OLD.financial_activity_at
          OR NEW.financial_retain_until IS DISTINCT FROM OLD.financial_retain_until THEN
          RAISE EXCEPTION 'Native financial clocks cannot be supplied' USING ERRCODE='42501';
        END IF;
        significant := (to_jsonb(NEW)-ARRAY['financial_activity_at','financial_retain_until'])
          IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['financial_activity_at','financial_retain_until']);
        IF TG_TABLE_NAME='connect_recipient_accounts' THEN
          significant := (to_jsonb(NEW)-ARRAY['financial_activity_at','financial_retain_until','capability_observed_at'])
            IS DISTINCT FROM (to_jsonb(OLD)-ARRAY['financial_activity_at','financial_retain_until','capability_observed_at']);
        END IF;
        IF significant THEN NEW.financial_activity_at := greatest(OLD.financial_activity_at,clock_timestamp()); END IF;
        IF TG_TABLE_NAME='connect_control_proofs' AND (to_jsonb(NEW)->>'accepted_at') IS NULL THEN
          NEW.financial_activity_at := NULL;
        END IF;
      END IF;
      NEW.financial_retain_until := ((NEW.financial_activity_at AT TIME ZONE 'UTC')+interval '7 years') AT TIME ZONE 'UTC';
      RETURN NEW;
    END $$""")
    op.execute("REVOKE ALL ON FUNCTION public.payment_financial_clock() FROM PUBLIC")
    op.execute("""CREATE FUNCTION public.payment_account_financial_epoch()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE source_record jsonb; source_id text; actor text; billing uuid;
      native_tenant uuid; canonical text[]:=ARRAY[]::text[]; captures text[]:=ARRAY[]::text[];
      source_subjects text[]; source_captures text[]; parent_source jsonb;
    BEGIN
      IF TG_OP='UPDATE' AND
        (to_jsonb(NEW)-ARRAY['financial_activity_at','financial_retain_until','capability_observed_at'])
          IS NOT DISTINCT FROM (to_jsonb(OLD)-ARRAY['financial_activity_at','financial_retain_until','capability_observed_at']) THEN RETURN NEW; END IF;
      FOR source_record IN SELECT item FROM unnest(CASE WHEN TG_OP='INSERT' THEN ARRAY[to_jsonb(NEW)]
        WHEN TG_OP='DELETE' THEN ARRAY[to_jsonb(OLD)] ELSE ARRAY[to_jsonb(OLD),to_jsonb(NEW)] END) item LOOP
        native_tenant := (source_record->>'tenant_id')::uuid;
        actor := coalesce(source_record->>'owner_sub',source_record->>'verified_by_sub',source_record->>'initiated_by_sub',
          source_record->'lifecycle'->'owner'->>'subject',source_record->'adoption'->>'owner_sub');
        source_id := coalesce(CASE WHEN TG_TABLE_NAME='host_payout_addresses' THEN (source_record->>'host_org_id')||':'||(source_record->>'chain_id') END,source_record->>'id',source_record->>'grant_id',source_record->>'revision_id',
          source_record->>'account_key',source_record->>'host_org_id');
        billing := (source_record->>'billing_record_id')::uuid;
        IF TG_TABLE_NAME='billing_tax_calculations' THEN
          SELECT o.billing_record_id INTO billing FROM public.billing_tax_orders o
            WHERE o.revision_id=(source_record->>'revision_id')::uuid AND o.tenant_id=native_tenant;
        ELSIF TG_TABLE_NAME='connect_access_results' THEN
          SELECT g.owner_sub INTO actor FROM public.connect_access_grants g
            WHERE g.id=(source_record->>'grant_id')::uuid AND g.tenant_id=native_tenant;
        END IF;
        SELECT array_agg(p.subject),array_agg(p.subject) FILTER(WHERE p.direct_reference)
          INTO source_subjects,source_captures FROM public.account_financial_parties(NULL,actor,native_tenant,
            'payment',TG_TABLE_NAME,source_id,CASE WHEN TG_TABLE_NAME='payer_mismatch_accounts' THEN source_record->>'account_key' END) p;
        canonical:=canonical||coalesce(source_subjects,ARRAY[]::text[]);
        IF TG_OP<>'DELETE' AND source_record=to_jsonb(NEW) THEN
          captures:=captures||coalesce(source_captures,ARRAY[]::text[]);
        END IF;
        IF billing IS NOT NULL THEN
          parent_source:=public.account_billing_financial_source(billing,native_tenant);
          IF parent_source IS NULL AND TG_OP='INSERT' THEN
            RAISE EXCEPTION 'Admitted payment parent required' USING ERRCODE='42501';
          END IF;
          SELECT array_agg(p.subject),array_agg(p.subject) FILTER(WHERE p.direct_reference)
            INTO source_subjects,source_captures FROM public.account_financial_parties(
              (parent_source->>'user_id')::uuid,parent_source->'metadata'->>'actor_sub',native_tenant,
              'billing','payment',billing::text) p;
          canonical:=canonical||coalesce(source_subjects,ARRAY[]::text[]);
          IF TG_OP<>'DELETE' AND source_record=to_jsonb(NEW) THEN captures:=captures||coalesce(source_captures,ARRAY[]::text[]); END IF;
        END IF;
      END LOOP;
      SELECT array_agg(DISTINCT item) INTO canonical FROM unnest(canonical) item WHERE item IS NOT NULL;
      SELECT coalesce(array_agg(DISTINCT item),ARRAY[]::text[]) INTO captures FROM unnest(captures) item WHERE item IS NOT NULL;
      PERFORM public.account_touch_financial_subjects(canonical,captures);
      IF TG_OP='DELETE' THEN RETURN OLD; END IF;
      IF TG_TABLE_NAME='payer_mismatch_accounts' AND
        ((TG_OP='INSERT' AND to_jsonb(NEW)->>'last_checkout_at' IS NOT NULL) OR
         (TG_OP='UPDATE' AND to_jsonb(NEW)->>'last_checkout_at' IS DISTINCT FROM to_jsonb(OLD)->>'last_checkout_at')) THEN
        PERFORM public.account_require_open_subjects(captures);
      END IF;
      PERFORM public.account_bind_financial_source(canonical,(to_jsonb(NEW)->>'tenant_id')::uuid,'payment',TG_TABLE_NAME,
        coalesce(CASE WHEN TG_TABLE_NAME='host_payout_addresses' THEN (to_jsonb(NEW)->>'host_org_id')||':'||(to_jsonb(NEW)->>'chain_id') END,to_jsonb(NEW)->>'id',to_jsonb(NEW)->>'grant_id',to_jsonb(NEW)->>'revision_id',to_jsonb(NEW)->>'account_key',to_jsonb(NEW)->>'host_org_id'));
      RETURN NEW;
    END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.payment_account_financial_epoch() FROM PUBLIC"
    )
    op.execute("""CREATE FUNCTION public.payment_account_new_authority()
    RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER
    SET search_path=pg_catalog SET row_security=off AS $$
    DECLARE actor text;
    BEGIN
      IF TG_OP='UPDATE' AND
        (to_jsonb(NEW)-ARRAY['financial_activity_at','financial_retain_until']) IS NOT DISTINCT FROM
        (to_jsonb(OLD)-ARRAY['financial_activity_at','financial_retain_until']) THEN RETURN NEW; END IF;
      actor:=coalesce(to_jsonb(NEW)->>'initiated_by_sub',to_jsonb(NEW)->>'owner_sub',to_jsonb(NEW)->>'verified_by_sub');
      IF actor IS NULL OR length(btrim(actor))=0 OR length(actor)>512 OR actor LIKE 'apikey:%' THEN
        RAISE EXCEPTION 'Native authenticated account initiator required' USING ERRCODE='42501';
      END IF;
      IF NOT pg_try_advisory_xact_lock(hashtextextended('identity-retirement:'||actor,0)) THEN
        RAISE EXCEPTION 'Account admission must retry' USING ERRCODE='40001';
      END IF;
      PERFORM public.account_require_open_subjects(ARRAY[actor]);
      RETURN NEW;
    END $$""")
    op.execute(
        "REVOKE ALL ON FUNCTION public.payment_account_new_authority() FROM PUBLIC"
    )
    op.execute(
        "CREATE TRIGGER account_financial_clock BEFORE INSERT OR UPDATE ON public.host_payout_addresses FOR EACH ROW EXECUTE FUNCTION public.payment_financial_clock()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_clock BEFORE INSERT OR UPDATE ON public.connect_recipient_accounts FOR EACH ROW EXECUTE FUNCTION public.payment_financial_clock()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_clock BEFORE INSERT OR UPDATE ON public.billing_tax_orders FOR EACH ROW EXECUTE FUNCTION public.payment_financial_clock()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_clock BEFORE INSERT OR UPDATE ON public.billing_tax_calculations FOR EACH ROW EXECUTE FUNCTION public.payment_financial_clock()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_clock BEFORE INSERT OR UPDATE ON public.connect_bank_approvals FOR EACH ROW EXECUTE FUNCTION public.payment_financial_clock()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_clock BEFORE INSERT OR UPDATE ON public.connect_reversal_exposure_observations FOR EACH ROW EXECUTE FUNCTION public.payment_financial_clock()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_clock BEFORE INSERT OR UPDATE ON public.connect_control_proofs FOR EACH ROW EXECUTE FUNCTION public.payment_financial_clock()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.host_payout_addresses FOR EACH ROW EXECUTE FUNCTION public.payment_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.connect_recipient_accounts FOR EACH ROW EXECUTE FUNCTION public.payment_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.billing_tax_orders FOR EACH ROW EXECUTE FUNCTION public.payment_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.billing_tax_calculations FOR EACH ROW EXECUTE FUNCTION public.payment_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.connect_bank_approvals FOR EACH ROW EXECUTE FUNCTION public.payment_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.connect_reversal_exposure_observations FOR EACH ROW EXECUTE FUNCTION public.payment_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.connect_control_proofs FOR EACH ROW EXECUTE FUNCTION public.payment_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.connect_access_states FOR EACH ROW EXECUTE FUNCTION public.payment_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.connect_access_grants FOR EACH ROW EXECUTE FUNCTION public.payment_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.connect_access_results FOR EACH ROW EXECUTE FUNCTION public.payment_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_epoch AFTER INSERT OR UPDATE OR DELETE ON public.payer_mismatch_accounts FOR EACH ROW EXECUTE FUNCTION public.payment_account_financial_epoch()"
    )
    op.execute(
        "CREATE TRIGGER account_new_authority BEFORE INSERT ON public.connect_recipient_accounts FOR EACH ROW EXECUTE FUNCTION public.payment_account_new_authority()"
    )
    op.execute(
        "CREATE TRIGGER account_new_authority BEFORE INSERT OR UPDATE ON public.host_payout_addresses FOR EACH ROW EXECUTE FUNCTION public.payment_account_new_authority()"
    )
    op.execute(
        "CREATE TRIGGER account_new_authority BEFORE INSERT ON public.connect_access_grants FOR EACH ROW EXECUTE FUNCTION public.payment_account_new_authority()"
    )
    op.execute(
        "CREATE TRIGGER account_new_authority BEFORE INSERT ON public.connect_control_proofs FOR EACH ROW EXECUTE FUNCTION public.payment_account_new_authority()"
    )
    op.execute(
        "CREATE TRIGGER account_new_authority BEFORE INSERT ON public.connect_bank_approvals FOR EACH ROW EXECUTE FUNCTION public.payment_account_new_authority()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.host_payout_addresses FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.connect_recipient_accounts FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.billing_tax_orders FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.billing_tax_calculations FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.connect_bank_approvals FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.connect_reversal_exposure_observations FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.connect_control_proofs FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.connect_access_states FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.connect_access_grants FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.connect_access_results FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute(
        "CREATE TRIGGER account_financial_not_truncated BEFORE TRUNCATE ON public.payer_mismatch_accounts FOR EACH STATEMENT EXECUTE FUNCTION public.account_refuse_financial_truncate()"
    )
    op.execute("SELECT public.account_register_financial_fence('payment',1)")


def downgrade():
    op.execute("SELECT public.account_lock_financial_fence_changes()")
    op.execute("SELECT public.account_unregister_financial_fence('payment')")
    op.execute(
        "DROP TRIGGER account_financial_not_truncated ON public.host_payout_addresses"
    )
    op.execute(
        "DROP TRIGGER account_financial_not_truncated ON public.connect_recipient_accounts"
    )
    op.execute(
        "DROP TRIGGER account_financial_not_truncated ON public.billing_tax_orders"
    )
    op.execute(
        "DROP TRIGGER account_financial_not_truncated ON public.billing_tax_calculations"
    )
    op.execute(
        "DROP TRIGGER account_financial_not_truncated ON public.connect_bank_approvals"
    )
    op.execute(
        "DROP TRIGGER account_financial_not_truncated ON public.connect_reversal_exposure_observations"
    )
    op.execute(
        "DROP TRIGGER account_financial_not_truncated ON public.connect_control_proofs"
    )
    op.execute(
        "DROP TRIGGER account_financial_not_truncated ON public.connect_access_states"
    )
    op.execute(
        "DROP TRIGGER account_financial_not_truncated ON public.connect_access_grants"
    )
    op.execute(
        "DROP TRIGGER account_financial_not_truncated ON public.connect_access_results"
    )
    op.execute(
        "DROP TRIGGER account_financial_not_truncated ON public.payer_mismatch_accounts"
    )

    op.execute("SET LOCAL row_security=off")
    op.execute("LOCK TABLE public.billing_tax_calculations IN ACCESS EXCLUSIVE MODE")
    op.execute("LOCK TABLE public.billing_tax_orders IN ACCESS EXCLUSIVE MODE")
    op.execute("LOCK TABLE public.connect_bank_approvals IN ACCESS EXCLUSIVE MODE")
    op.execute("LOCK TABLE public.connect_control_proofs IN ACCESS EXCLUSIVE MODE")
    op.execute("LOCK TABLE public.connect_recipient_accounts IN ACCESS EXCLUSIVE MODE")
    op.execute(
        "LOCK TABLE public.connect_reversal_exposure_observations IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("LOCK TABLE public.host_payout_addresses IN ACCESS EXCLUSIVE MODE")
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM public.host_payout_addresses\n          WHERE financial_activity_at IS NOT NULL OR financial_retain_until IS NOT NULL) THEN\n          RAISE EXCEPTION 'Recorded payment financial clocks cannot be discarded';\n        END IF; END $$"
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM public.connect_recipient_accounts\n          WHERE financial_activity_at IS NOT NULL OR financial_retain_until IS NOT NULL) THEN\n          RAISE EXCEPTION 'Recorded payment financial clocks cannot be discarded';\n        END IF; END $$"
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM public.billing_tax_orders\n          WHERE financial_activity_at IS NOT NULL OR financial_retain_until IS NOT NULL) THEN\n          RAISE EXCEPTION 'Recorded payment financial clocks cannot be discarded';\n        END IF; END $$"
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM public.billing_tax_calculations\n          WHERE financial_activity_at IS NOT NULL OR financial_retain_until IS NOT NULL) THEN\n          RAISE EXCEPTION 'Recorded payment financial clocks cannot be discarded';\n        END IF; END $$"
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM public.connect_bank_approvals\n          WHERE financial_activity_at IS NOT NULL OR financial_retain_until IS NOT NULL) THEN\n          RAISE EXCEPTION 'Recorded payment financial clocks cannot be discarded';\n        END IF; END $$"
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM public.connect_reversal_exposure_observations\n          WHERE financial_activity_at IS NOT NULL OR financial_retain_until IS NOT NULL) THEN\n          RAISE EXCEPTION 'Recorded payment financial clocks cannot be discarded';\n        END IF; END $$"
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS(SELECT 1 FROM public.connect_control_proofs\n          WHERE financial_activity_at IS NOT NULL OR financial_retain_until IS NOT NULL) THEN\n          RAISE EXCEPTION 'Recorded payment financial clocks cannot be discarded';\n        END IF; END $$"
    )
    op.execute("""DO $$ BEGIN IF EXISTS(SELECT 1 FROM public.connect_recipient_accounts
      WHERE initiated_by_sub IS NOT NULL) THEN
      RAISE EXCEPTION 'Native recipient initiators cannot be discarded';
    END IF; END $$""")
    op.execute(
        "DROP TRIGGER account_new_authority ON public.connect_recipient_accounts"
    )
    op.execute("DROP TRIGGER account_new_authority ON public.host_payout_addresses")
    op.execute("DROP TRIGGER account_new_authority ON public.connect_access_grants")
    op.execute("DROP TRIGGER account_new_authority ON public.connect_control_proofs")
    op.execute("DROP TRIGGER account_new_authority ON public.connect_bank_approvals")
    op.execute("DROP TRIGGER account_financial_epoch ON public.host_payout_addresses")
    op.execute(
        "DROP TRIGGER account_financial_epoch ON public.connect_recipient_accounts"
    )
    op.execute("DROP TRIGGER account_financial_epoch ON public.billing_tax_orders")
    op.execute(
        "DROP TRIGGER account_financial_epoch ON public.billing_tax_calculations"
    )
    op.execute("DROP TRIGGER account_financial_epoch ON public.connect_bank_approvals")
    op.execute(
        "DROP TRIGGER account_financial_epoch ON public.connect_reversal_exposure_observations"
    )
    op.execute("DROP TRIGGER account_financial_epoch ON public.connect_control_proofs")
    op.execute("DROP TRIGGER account_financial_epoch ON public.connect_access_states")
    op.execute("DROP TRIGGER account_financial_epoch ON public.connect_access_grants")
    op.execute("DROP TRIGGER account_financial_epoch ON public.connect_access_results")
    op.execute("DROP TRIGGER account_financial_epoch ON public.payer_mismatch_accounts")
    op.execute("DROP TRIGGER account_financial_clock ON public.host_payout_addresses")
    op.drop_index(
        "ix_host_payout_addresses_financial_due", table_name="host_payout_addresses"
    )
    op.drop_constraint(
        "ck_host_payout_addresses_financial_clock",
        "host_payout_addresses",
        type_="check",
    )
    op.drop_column("host_payout_addresses", "financial_retain_until")
    op.drop_column("host_payout_addresses", "financial_activity_at")
    op.execute(
        "DROP TRIGGER account_financial_clock ON public.connect_recipient_accounts"
    )
    op.drop_index(
        "ix_connect_recipient_accounts_financial_due",
        table_name="connect_recipient_accounts",
    )
    op.drop_constraint(
        "ck_connect_recipient_accounts_financial_clock",
        "connect_recipient_accounts",
        type_="check",
    )
    op.drop_column("connect_recipient_accounts", "financial_retain_until")
    op.drop_column("connect_recipient_accounts", "financial_activity_at")
    op.execute("DROP TRIGGER account_financial_clock ON public.billing_tax_orders")
    op.drop_index(
        "ix_billing_tax_orders_financial_due", table_name="billing_tax_orders"
    )
    op.drop_constraint(
        "ck_billing_tax_orders_financial_clock", "billing_tax_orders", type_="check"
    )
    op.drop_column("billing_tax_orders", "financial_retain_until")
    op.drop_column("billing_tax_orders", "financial_activity_at")
    op.execute(
        "DROP TRIGGER account_financial_clock ON public.billing_tax_calculations"
    )
    op.drop_index(
        "ix_billing_tax_calculations_financial_due",
        table_name="billing_tax_calculations",
    )
    op.drop_constraint(
        "ck_billing_tax_calculations_financial_clock",
        "billing_tax_calculations",
        type_="check",
    )
    op.drop_column("billing_tax_calculations", "financial_retain_until")
    op.drop_column("billing_tax_calculations", "financial_activity_at")
    op.execute("DROP TRIGGER account_financial_clock ON public.connect_bank_approvals")
    op.drop_index(
        "ix_connect_bank_approvals_financial_due", table_name="connect_bank_approvals"
    )
    op.drop_constraint(
        "ck_connect_bank_approvals_financial_clock",
        "connect_bank_approvals",
        type_="check",
    )
    op.drop_column("connect_bank_approvals", "financial_retain_until")
    op.drop_column("connect_bank_approvals", "financial_activity_at")
    op.execute(
        "DROP TRIGGER account_financial_clock ON public.connect_reversal_exposure_observations"
    )
    op.drop_index(
        "ix_connect_reversal_exposure_observations_financial_due",
        table_name="connect_reversal_exposure_observations",
    )
    op.drop_constraint(
        "ck_connect_reversal_exposure_observations_financial_clock",
        "connect_reversal_exposure_observations",
        type_="check",
    )
    op.drop_column("connect_reversal_exposure_observations", "financial_retain_until")
    op.drop_column("connect_reversal_exposure_observations", "financial_activity_at")
    op.execute("DROP TRIGGER account_financial_clock ON public.connect_control_proofs")
    op.drop_index(
        "ix_connect_control_proofs_financial_due", table_name="connect_control_proofs"
    )
    op.drop_constraint(
        "ck_connect_control_proofs_financial_clock",
        "connect_control_proofs",
        type_="check",
    )
    op.drop_column("connect_control_proofs", "financial_retain_until")
    op.drop_column("connect_control_proofs", "financial_activity_at")
    op.execute("DROP FUNCTION public.payment_account_new_authority()")
    op.execute("DROP FUNCTION public.payment_account_financial_epoch()")
    op.execute("DROP FUNCTION public.payment_financial_clock()")
    op.execute(ORIGINAL_PROGRESS)
    op.execute("""CREATE OR REPLACE FUNCTION public.control_proof_once() RETURNS trigger
    LANGUAGE plpgsql SET search_path=pg_catalog AS $$ BEGIN
      IF OLD.report IS NOT NULL OR NEW.report IS NULL OR NEW.accepted_at IS NULL OR
        (to_jsonb(NEW)-ARRAY['report','accepted_at']) IS DISTINCT FROM
        (to_jsonb(OLD)-ARRAY['report','accepted_at']) THEN
        RAISE EXCEPTION 'Host-control proof history is immutable' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$""")
    op.drop_constraint(
        "ck_recipient_initiator", "connect_recipient_accounts", type_="check"
    )
    op.drop_column("connect_recipient_accounts", "initiated_by_sub")
