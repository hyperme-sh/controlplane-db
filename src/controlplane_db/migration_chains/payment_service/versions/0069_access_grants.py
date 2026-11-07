"""Explicit legacy policy and immutable, tenant-scoped Account Session journal."""

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "payment_service_0069_access"
down_revision = "payment_service_0068_adoption"
branch_labels = None
depends_on = None


def legacy_operations(billing_id, host, account, transfer, bank):
    """Freeze pre-upgrade uncertainty without rewriting any financial journal."""
    operations = {}

    def mapping(value):
        return value if isinstance(value, dict) else {}

    def matches(scope):
        return scope.get("host_org_id") == str(host) or (
            account is not None and scope.get("account_id") == account
        )

    transfer, bank = mapping(transfer), mapping(bank)
    if transfer and matches(transfer):
        # A prepared/cancelled/skipped intent proves no POST; a native bound
        # transfer proves creation resolved. Everything else stays conservative.
        native_id = transfer.get("transfer_id")
        resolved = (
            isinstance(native_id, str)
            and native_id.startswith("tr_")
            and len(native_id) > 3
        )
        if not resolved and transfer.get("status") not in {
            "prepared",
            "cancelled",
            "skipped",
            "waiting_recipient",
        }:
            operations[f"transfer:{billing_id}"] = True
        reversal = mapping(transfer.get("reversal"))
        if transfer.get("reversal") is not None:
            target = reversal.get("target_cents")
            key = (
                f"reversal:{billing_id}:{target}"
                if type(target) is int and target > 0
                else f"legacy-reversal:{billing_id}"
            )
            operations[key] = True
    plan = mapping(bank.get("plan"))
    native_id = bank.get("payout_id")
    resolved = (
        isinstance(native_id, str)
        and native_id.startswith("po_")
        and len(native_id) > 3
    )
    if bank and matches(plan) and not resolved:
        attempts = bank.get("attempts")
        unsent = isinstance(attempts, list) and (
            (
                bool(attempts)
                and all(
                    isinstance(attempt, dict) and attempt.get("outcome") == "not_sent"
                    for attempt in attempts
                )
            )
            or (
                not attempts
                and bank.get("status") in {"prepared", "waiting_readiness", "skipped"}
            )
        )
        if not unsent and bank.get("status") != "skipped":
            try:
                key = "bank:" + str(uuid.UUID(str(plan.get("plan_id"))))
            except (ValueError, TypeError, AttributeError):
                key = f"legacy-bank:{billing_id}"
            operations[key] = True
    return operations


def seed_legacy_operations():
    # A migration role unable to see every tenant must fail rather than silently
    # create apparently clear fences. This is a read-only billing-owner exception.
    op.execute("SET LOCAL row_security = off")
    connection = op.get_bind()
    rows = connection.execute(
        sa.text("""
        SELECT r.tenant_id, r.host_org_id, r.stripe_account_id, b.id AS billing_id,
               b.metadata->'stripe_connect_transfer' AS transfer,
               b.metadata->'stripe_bank_payout' AS bank
        FROM connect_recipient_accounts r JOIN billing_records b
          ON b.tenant_id = r.tenant_id
        WHERE b.metadata->'stripe_connect_transfer'->>'host_org_id' = r.host_org_id::text
           OR b.metadata->'stripe_connect_transfer'->>'account_id' = r.stripe_account_id
           OR b.metadata->'stripe_bank_payout'->'plan'->>'host_org_id' = r.host_org_id::text
           OR b.metadata->'stripe_bank_payout'->'plan'->>'account_id' = r.stripe_account_id
    """)
    )
    update = sa.text("""UPDATE connect_access_states
        SET money_operations = money_operations || :operations
        WHERE tenant_id = :tenant AND host_org_id = :host""").bindparams(
        sa.bindparam("operations", type_=JSONB)
    )
    for row in rows.mappings():
        operations = legacy_operations(
            row["billing_id"],
            row["host_org_id"],
            row["stripe_account_id"],
            row["transfer"],
            row["bank"],
        )
        if operations:
            connection.execute(
                update,
                {
                    "operations": operations,
                    "tenant": row["tenant_id"],
                    "host": row["host_org_id"],
                },
            )


def upgrade():
    op.create_table(
        "connect_access_states",
        sa.Column("tenant_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("host_org_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("policy", sa.String(32), nullable=False),
        sa.Column("epoch", sa.BigInteger(), nullable=False, server_default="1"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "money_operations",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "host_org_id"],
            [
                "connect_recipient_accounts.tenant_id",
                "connect_recipient_accounts.host_org_id",
            ],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "policy IN ('express-probe/v1', 'embedded-api/v1')", name="ck_access_policy"
        ),
        sa.CheckConstraint("epoch >= 1", name="ck_access_epoch"),
        sa.CheckConstraint(
            "jsonb_typeof(money_operations) = 'object'", name="ck_access_money"
        ),
    )
    op.execute("ALTER TABLE public.connect_recipient_accounts NO FORCE ROW LEVEL SECURITY")
    # Backfill and future enrollment are explicitly legacy, never silently embedded.
    op.execute(
        "INSERT INTO connect_access_states(tenant_id,host_org_id,policy) SELECT tenant_id,host_org_id,'express-probe/v1' FROM connect_recipient_accounts"
    )
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT FROM public.connect_recipient_accounts)")):
        seed_legacy_operations()
    op.execute("ALTER TABLE public.connect_recipient_accounts FORCE ROW LEVEL SECURITY")
    op.execute("""
    CREATE FUNCTION public.connect_access_legacy() RETURNS trigger
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$ BEGIN
      INSERT INTO public.connect_access_states(tenant_id,host_org_id,policy)
      VALUES (NEW.tenant_id,NEW.host_org_id,'express-probe/v1'); RETURN NEW;
    END $$;
    CREATE TRIGGER connect_access_legacy AFTER INSERT ON public.connect_recipient_accounts
    FOR EACH ROW EXECUTE FUNCTION public.connect_access_legacy();
    CREATE FUNCTION public.connect_access_epoch() RETURNS trigger
    LANGUAGE plpgsql SET search_path = pg_catalog AS $$ BEGIN
      IF NEW.tenant_id <> OLD.tenant_id OR NEW.host_org_id <> OLD.host_org_id OR
         NEW.epoch < OLD.epoch OR
         ((NEW.policy,NEW.enabled) IS DISTINCT FROM (OLD.policy,OLD.enabled) AND NEW.epoch <= OLD.epoch) THEN
        RAISE EXCEPTION 'Access authority requires a new epoch' USING ERRCODE = '23514';
      END IF; RETURN NEW;
    END $$;
    CREATE TRIGGER connect_access_epoch BEFORE UPDATE ON public.connect_access_states
    FOR EACH ROW EXECUTE FUNCTION public.connect_access_epoch();
    """)
    op.create_table(
        "connect_access_grants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("host_org_id", UUID(as_uuid=True), nullable=False),
        sa.Column("enrollment_attempt_id", UUID(as_uuid=True), nullable=False),
        sa.Column("platform_id", sa.String(255), nullable=False),
        sa.Column("account_id", sa.String(255), nullable=False),
        sa.Column("owner_sub", sa.String(512), nullable=False),
        sa.Column("member_id", sa.String(512), nullable=False),
        sa.Column("issuer_session", sa.String(512), nullable=False),
        sa.Column("purpose", sa.String(16), nullable=False),
        sa.Column("policy", sa.String(32), nullable=False),
        sa.Column("policy_hash", sa.String(64), nullable=False),
        sa.Column("epoch", sa.BigInteger(), nullable=False),
        sa.Column("parameters", JSONB(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "host_org_id"],
            ["connect_access_states.tenant_id", "connect_access_states.host_org_id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("id", "tenant_id", name="uq_access_grant_tenant"),
        sa.CheckConstraint(
            "purpose IN ('view', 'onboarding', 'maintenance')", name="ck_access_purpose"
        ),
        sa.CheckConstraint(
            "epoch >= 1 AND policy = 'embedded-api/v1'", name="ck_grant_policy"
        ),
        sa.CheckConstraint("policy_hash ~ '^[0-9a-f]{64}$'", name="ck_grant_hash"),
        sa.CheckConstraint(
            "jsonb_typeof(parameters) = 'object'", name="ck_grant_parameters"
        ),
        sa.CheckConstraint(
            "length(owner_sub) BETWEEN 1 AND 512 AND length(issuer_session) BETWEEN 1 AND 512 AND length(member_id) BETWEEN 1 AND 512",
            name="ck_grant_actor",
        ),
    )
    op.create_index(
        "ix_connect_access_grants_tenant_id", "connect_access_grants", ["tenant_id"]
    )
    op.create_table(
        "connect_access_results",
        sa.Column(
            "grant_id",
            UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_id", sa.String(255), nullable=False),
        sa.Column("permissions", JSONB(), nullable=False),
        sa.ForeignKeyConstraint(
            ["grant_id", "tenant_id"],
            ["connect_access_grants.id", "connect_access_grants.tenant_id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "request_id ~ '^req_[A-Za-z0-9_]{1,200}$' AND jsonb_typeof(permissions) = 'object'",
            name="ck_access_result_provenance",
        ),
    )
    op.create_index(
        "ix_connect_access_results_tenant_id", "connect_access_results", ["tenant_id"]
    )
    condition = (
        "tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid"
    )
    for table in (
        "connect_access_states",
        "connect_access_grants",
        "connect_access_results",
    ):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        for operation, clause in (
            ("SELECT", f"USING ({condition})"),
            ("INSERT", f"WITH CHECK ({condition})"),
            ("UPDATE", f"USING ({condition}) WITH CHECK ({condition})"),
        ):
            op.execute(
                f"CREATE POLICY {table}_{operation.lower()} ON {table} FOR {operation} {clause}"
            )
        for operation in ("DELETE", "TRUNCATE"):
            op.execute(
                f"CREATE TRIGGER {table}_{operation.lower()} BEFORE {operation} ON public.{table} FOR EACH {'STATEMENT' if operation == 'TRUNCATE' else 'ROW'} EXECUTE FUNCTION public.connect_recipient_immutable()"
            )
        if table != "connect_access_states":
            op.execute(
                f"CREATE TRIGGER {table}_update BEFORE UPDATE ON public.{table} FOR EACH ROW EXECUTE FUNCTION public.connect_recipient_immutable()"
            )


def downgrade():
    op.execute("SET LOCAL row_security = off")
    op.execute(
        "LOCK TABLE public.connect_access_states, public.connect_access_grants, public.connect_access_results IN ACCESS EXCLUSIVE MODE"
    )
    op.execute("""DO $$ BEGIN
      IF EXISTS(SELECT 1 FROM public.connect_access_grants) OR EXISTS(SELECT 1 FROM public.connect_access_states WHERE policy <> 'express-probe/v1' OR enabled OR epoch <> 1 OR money_operations <> '{}'::jsonb) THEN
        RAISE EXCEPTION 'Cannot remove access authority or issuance history';
      END IF;
    END $$;""")
    op.execute(
        "DROP TRIGGER connect_access_legacy ON public.connect_recipient_accounts"
    )
    op.drop_table("connect_access_results")
    op.drop_table("connect_access_grants")
    op.drop_table("connect_access_states")
    op.execute("DROP FUNCTION public.connect_access_legacy()")
    op.execute("DROP FUNCTION public.connect_access_epoch()")
