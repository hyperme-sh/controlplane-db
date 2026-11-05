"""Native TEST policy cannot be enabled by a request flag or ordinary database role."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError


def test_policy_is_database_bound_and_default_off(migrated_postgres):
    engine = create_engine(migrated_postgres)
    try:
        with engine.begin() as c:
            assert c.scalar(text("SELECT public.account_test_data_enabled()")) is False
            c.execute(text("SELECT set_config('app.test_retention','true',true)"))
            assert c.scalar(text("SELECT public.account_test_data_enabled()")) is False
            c.execute(
                text(
                    "INSERT INTO account_test_data_policy(singleton,database_oid,database_name,enabled) VALUES(true,(SELECT oid FROM pg_database WHERE datname=current_database()),current_database(),true)"
                )
            )
            assert c.scalar(text("SELECT public.account_test_data_enabled()")) is True
            c.execute(
                text(
                    "UPDATE account_test_data_policy SET database_name='another_database'"
                )
            )
            assert c.scalar(text("SELECT public.account_test_data_enabled()")) is False
            c.execute(
                text(
                    "UPDATE account_test_data_policy SET database_name=current_database(),cluster_identifier='another-cluster'"
                )
            )
            assert c.scalar(text("SELECT public.account_test_data_enabled()")) is False
    finally:
        engine.dispose()


def test_untrusted_role_cannot_enable_test_or_mint_delete_capabilities(
    migrated_postgres,
):
    engine = create_engine(migrated_postgres)
    try:
        with engine.begin() as c:
            c.execute(text("CREATE ROLE test_retention_untrusted NOLOGIN NOBYPASSRLS"))
            c.execute(text("SET LOCAL ROLE test_retention_untrusted"))
        for stmt in (
            "SELECT public.account_test_data_enabled()",
            "SELECT public.account_test_row_delete_allowed(0,'{}'::jsonb)",
            "INSERT INTO account_test_data_policy(singleton,database_oid,database_name,enabled) VALUES(true,0,current_database(),true)",
            "INSERT INTO account_test_delete_capabilities VALUES(pg_current_xact_id()::text,0,decode('00','hex'))",
        ):
            with pytest.raises(DBAPIError):
                with engine.begin() as c:
                    c.execute(text("SET LOCAL ROLE test_retention_untrusted"))
                    c.execute(text(stmt))
    finally:
        with engine.begin() as c:
            c.execute(text("DROP ROLE test_retention_untrusted"))
        engine.dispose()


def test_capability_must_be_exact_and_cannot_survive_commit(migrated_postgres):
    engine = create_engine(migrated_postgres)
    try:
        with pytest.raises(DBAPIError, match="cannot survive commit"):
            with engine.begin() as c:
                c.execute(
                    text(
                        "INSERT INTO account_test_data_policy(singleton,database_oid,database_name,enabled) VALUES(true,(SELECT oid FROM pg_database WHERE datname=current_database()),current_database(),true)"
                    )
                )
                c.execute(
                    text(
                        "INSERT INTO account_test_delete_capabilities VALUES(pg_current_xact_id()::text,'public.billing_records'::regclass,sha256(convert_to('{}'::jsonb::text,'UTF8')))"
                    )
                )
                assert (
                    c.scalar(
                        text(
                            "SELECT public.account_test_row_delete_allowed('public.billing_records'::regclass,'{}'::jsonb)"
                        )
                    )
                    is True
                )
                assert (
                    c.scalar(
                        text(
                            "SELECT public.account_test_row_delete_allowed('public.billing_records'::regclass,CAST(:row AS jsonb))"
                        ),
                        {"row": '{"id":1}'},
                    )
                    is False
                )
        with engine.begin() as c:
            assert (
                c.scalar(text("SELECT count(*) FROM account_test_delete_capabilities"))
                == 0
            )
    finally:
        engine.dispose()


def seed_closed_payer(connection, *, tenant=None, before_close=None):
    import json, uuid

    subject = str(uuid.uuid4())
    user = uuid.uuid4()
    payment = uuid.uuid4()
    if tenant:
        connection.execute(
            text("INSERT INTO tenants(id,name,is_active) VALUES(:t,:n,true)"),
            {"t": tenant, "n": str(tenant)},
        )
    connection.execute(
        text(
            "INSERT INTO users(id,tenant_id,first_name,last_name,email,gender,is_active,keycloak_sub) VALUES(:u,:t,'Test','Payer',:email,'unspecified',true,:s)"
        ),
        {"u": user, "t": tenant, "s": subject, "email": subject + "@example.invalid"},
    )
    connection.execute(
        text(
            "INSERT INTO billing_records(id,tenant_id,scope,actor,user_id,payment_type,currency,amount,status,metadata) VALUES(:p,:t,'lease','user',:u,'card','USD',1234,'pending',CAST(:m AS jsonb))"
        ),
        {
            "p": payment,
            "t": tenant,
            "u": user,
            "m": json.dumps({"actor_sub": subject, "unsettled_test_obligation": True}),
        },
    )
    if before_close:
        before_close(connection, subject, user, payment, tenant)
    at = connection.scalar(text("SELECT transaction_timestamp()"))
    connection.execute(
        text("INSERT INTO identity_retirements VALUES(:s,:at)"),
        {"s": subject, "at": at},
    )
    effects = {
        "processor_version": 1,
        "identity": {"disabled": True},
        "scope_discovery": True,
        "scope_tenants": [str(tenant)] if tenant else [],
        "platform_profile": {
            "user_ids": [] if tenant else [str(user)],
            "profile_inventory_complete": True,
        },
    }
    connection.execute(
        text(
            "INSERT INTO account_lifecycles(subject,requested_at,requested_by,source,state,closed_at,retry_at,financial_hold,hold_reference,effects) VALUES(:s,:at,:s,'self_service','closed',:at,:at,true,'test-hold',CAST(:e AS jsonb))"
        ),
        {"s": subject, "at": at, "e": json.dumps(effects)},
    )
    if tenant:
        connection.execute(
            text(
                "INSERT INTO account_lifecycle_scopes(tenant_id,subject,user_ids,effects) VALUES(:t,:s,CAST(:ids AS jsonb),CAST(:e AS jsonb))"
            ),
            {
                "t": tenant,
                "s": subject,
                "ids": json.dumps([str(user)]),
                "e": json.dumps({"profile_inventory_complete": True}),
            },
        )
    for tid in [None, tenant] if tenant else [None]:
        for function in (
            "account_prime_billing_financial_sources",
            "payment_prime_financial_sources",
            "hypermesh_prime_financial_sources",
        ):
            receipt = connection.scalar(
                text(f"SELECT public.{function}(:s,:at,:t,100)"),
                {"s": subject, "at": at, "t": tid},
            )
            assert receipt["complete"] is True
    return subject, at, user, payment


def test_real_test_closure_purges_recent_unsettled_payment_despite_hold(
    migrated_postgres,
):
    from controlplane_db.test_retention import purge_test_finances

    engine = create_engine(migrated_postgres)
    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(c)
        with engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO account_test_data_policy(singleton,database_oid,database_name,enabled) VALUES(true,(SELECT oid FROM pg_database WHERE datname=current_database()),current_database(),true)"
                )
            )
            receipt = purge_test_finances(c, subject, at)
            assert (
                receipt["complete"] is True
                and receipt["tables"]["billing_records"] == 1
            )
        with engine.begin() as c:
            assert (
                c.scalar(
                    text("SELECT count(*) FROM billing_records WHERE id=:p"),
                    {"p": payment},
                )
                == 0
            )
            assert (
                c.scalar(
                    text(
                        "SELECT count(*) FROM account_financial_source_bindings WHERE subject=:s"
                    ),
                    {"s": subject},
                )
                == 0
            )
            assert (
                c.scalar(text("SELECT count(*) FROM account_test_delete_capabilities"))
                == 0
            )
    finally:
        engine.dispose()


def test_production_keeps_recent_payment_and_hold_even_with_request_guc(
    migrated_postgres, monkeypatch
):
    from controlplane_db.test_retention import (
        purge_test_finances,
        TestRetentionUnavailable,
    )

    engine = create_engine(migrated_postgres)
    monkeypatch.setenv("FASTAPI_ENV", "test")
    monkeypatch.setenv("ACCOUNT_CLOSURE_RETENTION", "none")
    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(c)
        with pytest.raises(TestRetentionUnavailable, match="not configured"):
            with engine.begin() as c:
                c.execute(text("SELECT set_config('app.test_retention','true',true)"))
                purge_test_finances(c, subject, at)
        with engine.begin() as c:
            assert (
                c.scalar(
                    text("SELECT count(*) FROM billing_records WHERE id=:p"),
                    {"p": payment},
                )
                == 1
            )
            assert (
                c.scalar(
                    text(
                        "SELECT financial_hold FROM account_lifecycles WHERE subject=:s"
                    ),
                    {"s": subject},
                )
                is True
            )
    finally:
        engine.dispose()


def test_orders_tax_and_payout_children_are_erased_without_settlement_or_age(
    migrated_postgres,
):
    import uuid
    from controlplane_db.test_retention import purge_test_finances

    engine = create_engine(migrated_postgres)
    tax, lease = uuid.uuid4(), uuid.uuid4()

    def children(c, subject, user, payment, tenant):
        params = {
            "p": payment,
            "t": tenant,
            "u": user,
            "tax": tax,
            "lease": lease,
            "host": uuid.uuid4(),
        }
        c.execute(
            text("UPDATE billing_records SET payment_type='usdc' WHERE id=:p"), params
        )
        c.execute(
            text("""INSERT INTO billing_tax_orders(revision_id,tenant_id,billing_record_id,seller_id,supply,fee_payer,policy_version,tax_code,subtotal_cents,country,state,postal_code,city,line1,line2)
          VALUES(:tax,:t,:p,:host,'owned','host','EXAMPLE-test','txcd_00000000',1234,'US','CA','00000','Test City','Fixture','')"""),
            params,
        )
        c.execute(
            text(
                "INSERT INTO billing_tax_calculations(revision_id,tenant_id,attempted_at) VALUES(:tax,:t,now())"
            ),
            params,
        )
        c.execute(
            text("""INSERT INTO hypermesh_leases(id,tenant_id,kind,status,renter_user_id,class_id,host_org_id,billing_record_id,reserved_hours,created_at,token_count,loaded_hours,purpose)
          VALUES(:lease,:t,'p1_hardware','active',:u,'test-class',:host,:p,1,now(),0,0,'renter')"""),
            params,
        )
        c.execute(
            text("""INSERT INTO hypermesh_payouts(lease_id,tenant_id,host_org_id,host_pubkey,kind,gross_cents,stripe_cut_cents,platform_take_cents,take_bps,net_cents,net_usdc_atoms)
          VALUES(:lease,:t,:host,'test-host','p1_hardware',1234,0,234,1900,1000,10000000)"""),
            params,
        )

    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(
                c, tenant=uuid.uuid4(), before_close=children
            )
            other, other_at, other_user, other_payment = seed_closed_payer(c)
        # A production guard still refuses a direct recent tax DELETE.
        with pytest.raises(DBAPIError, match="Tax history"):
            with engine.begin() as c:
                c.execute(
                    text("DELETE FROM billing_tax_calculations WHERE revision_id=:tax"),
                    {"tax": tax},
                )
        with engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO account_test_data_policy(singleton,database_oid,database_name,enabled) VALUES(true,(SELECT oid FROM pg_database WHERE datname=current_database()),current_database(),true)"
                )
            )
            receipt = purge_test_finances(c, subject, at)
            assert receipt["complete"] is True
            for name in (
                "billing_records",
                "billing_tax_orders",
                "billing_tax_calculations",
                "hypermesh_leases",
                "hypermesh_payouts",
            ):
                assert receipt["tables"][name] == 1
        with engine.begin() as c:
            assert (
                c.scalar(
                    text("SELECT count(*) FROM billing_records WHERE id=:p"),
                    {"p": other_payment},
                )
                == 1
            )
            assert c.scalar(text("SELECT count(*) FROM billing_tax_orders")) == 0
            assert c.scalar(text("SELECT count(*) FROM hypermesh_payouts")) == 0
    finally:
        engine.dispose()


def enable_test_policy(c):
    c.execute(
        text(
            "INSERT INTO account_test_data_policy(singleton,database_oid,database_name,enabled) VALUES(true,(SELECT oid FROM pg_database WHERE datname=current_database()),current_database(),true)"
        )
    )


def test_production_native_hold_and_seven_year_guards_remain_enforced(
    migrated_postgres,
):
    engine = create_engine(migrated_postgres)
    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(c)
        with pytest.raises(DBAPIError, match="Financial erasure authority"):
            with engine.begin() as c:
                c.execute(
                    text("SELECT public.account_lock_financial_erasure(:s,:at,NULL)"),
                    {"s": subject, "at": at},
                )
        with engine.begin() as c:
            c.execute(
                text(
                    "UPDATE account_lifecycles SET financial_hold=false WHERE subject=:s"
                ),
                {"s": subject},
            )
        with pytest.raises(DBAPIError, match="seven-year financial retention"):
            with engine.begin() as c:
                c.execute(
                    text("""SELECT public.account_issue_financial_transition(:s,:at,NULL,ARRAY[CAST(:s AS text)],
                  'billing','billing_records',b.id::text,to_jsonb(b),NULL,NULL) FROM billing_records b WHERE b.id=:p"""),
                    {"s": subject, "at": at, "p": payment},
                )
        with engine.begin() as c:
            assert (
                c.scalar(
                    text("SELECT count(*) FROM billing_records WHERE id=:p"),
                    {"p": payment},
                )
                == 1
            )
    finally:
        engine.dispose()


def test_incomplete_original_closure_cannot_purge_even_in_test(migrated_postgres):
    from datetime import timedelta
    from controlplane_db.test_retention import purge_test_finances

    engine = create_engine(migrated_postgres)
    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(c)
            enable_test_policy(c)
        with pytest.raises(DBAPIError, match="Original closed financial inventory"):
            with engine.begin() as c:
                purge_test_finances(c, subject, at + timedelta(seconds=1))
        with engine.begin() as c:
            assert (
                c.scalar(
                    text("SELECT count(*) FROM billing_records WHERE id=:p"),
                    {"p": payment},
                )
                == 1
            )
    finally:
        engine.dispose()


def test_native_delete_failure_rolls_back_all_rows_and_capabilities(migrated_postgres):
    from controlplane_db.test_retention import purge_test_finances

    engine = create_engine(migrated_postgres)
    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(c)
            enable_test_policy(c)
            c.execute(
                text(
                    "CREATE FUNCTION test_purge_failure() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'planned cleanup failure'; END $$"
                )
            )
            c.execute(
                text(
                    "CREATE TRIGGER zz_test_purge_failure AFTER DELETE ON billing_records FOR EACH ROW EXECUTE FUNCTION test_purge_failure()"
                )
            )
        with pytest.raises(DBAPIError, match="planned cleanup failure"):
            with engine.begin() as c:
                purge_test_finances(c, subject, at)
        with engine.begin() as c:
            assert (
                c.scalar(
                    text("SELECT count(*) FROM billing_records WHERE id=:p"),
                    {"p": payment},
                )
                == 1
            )
            assert (
                c.scalar(text("SELECT count(*) FROM account_test_delete_capabilities"))
                == 0
            )
    finally:
        engine.dispose()


def test_unknown_dependency_owner_is_pending_not_silently_deleted(migrated_postgres):
    from controlplane_db.test_retention import (
        purge_test_finances,
        TestRetentionUnavailable,
    )

    engine = create_engine(migrated_postgres)
    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(c)
            enable_test_policy(c)
            c.execute(
                text(
                    "CREATE TABLE future_owner_data(payment_id uuid REFERENCES billing_records(id),payload text)"
                )
            )
            c.execute(
                text(
                    "INSERT INTO future_owner_data VALUES(:p,'preserve unknown owner')"
                ),
                {"p": payment},
            )
        with pytest.raises(
            TestRetentionUnavailable, match="Unrecognized financial dependency owner"
        ):
            with engine.begin() as c:
                purge_test_finances(c, subject, at)
        with engine.begin() as c:
            assert c.scalar(text("SELECT count(*) FROM future_owner_data")) == 1
            assert (
                c.scalar(
                    text("SELECT count(*) FROM billing_records WHERE id=:p"),
                    {"p": payment},
                )
                == 1
            )
    finally:
        engine.dispose()


def test_small_batches_do_not_report_completion_with_other_roots_remaining(
    migrated_postgres,
):
    import uuid, json
    from controlplane_db.test_retention import purge_test_finances

    engine = create_engine(migrated_postgres)

    def extra(c, subject, user, payment, tenant):
        c.execute(
            text(
                "INSERT INTO billing_records(id,scope,actor,user_id,payment_type,currency,amount,status,metadata) VALUES(:p,'lease','user',:u,'card','USD',1234,'pending',CAST(:m AS jsonb))"
            ),
            {"p": uuid.uuid4(), "u": user, "m": json.dumps({"actor_sub": subject})},
        )

    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(c, before_close=extra)
            enable_test_policy(c)
        with engine.begin() as c:
            receipt = purge_test_finances(c, subject, at, limit=1)
            assert receipt["complete"] is False and receipt["deleted"] == 1
        with engine.begin() as c:
            receipt = purge_test_finances(c, subject, at, limit=1)
            assert receipt["complete"] is True and receipt["deleted"] == 1
        with engine.begin() as c:
            assert c.scalar(text("SELECT count(*) FROM billing_records")) == 0
    finally:
        engine.dispose()


def test_test_policy_downgrade_requires_restoring_owner_guards_first(migrated_postgres):
    from alembic import command
    from controlplane_db import migrations

    engine = create_engine(migrated_postgres)
    try:
        with pytest.raises(DBAPIError, match="Restore native owner delete guards"):
            with engine.begin() as c:
                command.downgrade(
                    migrations._config(migrations._ROOT, "platform", c),
                    "platform_0079_closure_merge",
                )
        with engine.begin() as c:
            assert (
                c.scalar(
                    text(
                        "SELECT to_regclass('public.account_test_delete_guard_originals') IS NOT NULL"
                    )
                )
                is True
            )
            assert c.scalar(text("SELECT public.account_test_data_enabled()")) is False
    finally:
        engine.dispose()


def test_downgrade_restores_original_production_guards_and_preserves_finances(
    migrated_postgres,
):
    from alembic import command
    from controlplane_db import migrations

    engine = create_engine(migrated_postgres)
    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(c)
            command.downgrade(
                migrations._config(migrations._ROOT, "payment_service", c),
                "payment_service_0080_fin_state",
            )
            command.downgrade(
                migrations._config(migrations._ROOT, "platform", c),
                "platform_0079_closure_merge",
            )
            assert (
                c.scalar(
                    text("SELECT count(*) FROM billing_records WHERE id=:p"),
                    {"p": payment},
                )
                == 1
            )
            assert (
                c.scalar(
                    text(
                        "SELECT to_regprocedure('public.account_test_data_enabled()') IS NULL"
                    )
                )
                is True
            )
            assert "account_test_row_delete_allowed" not in c.scalar(
                text(
                    "SELECT prosrc FROM pg_proc WHERE oid='public.tax_history_retained()'::regprocedure"
                )
            )
        with pytest.raises(DBAPIError, match="Financial erasure authority"):
            with engine.begin() as c:
                c.execute(
                    text("SELECT public.account_lock_financial_erasure(:s,:at,NULL)"),
                    {"s": subject, "at": at},
                )
    finally:
        engine.dispose()


def test_successful_delete_capability_serializes_disabling_test_mode(migrated_postgres):
    engine = create_engine(migrated_postgres)
    try:
        with engine.begin() as c:
            enable_test_policy(c)
        with engine.begin() as c:
            c.execute(
                text(
                    "INSERT INTO account_test_delete_capabilities VALUES(pg_current_xact_id()::text,'public.billing_records'::regclass,sha256(convert_to('{}'::jsonb::text,'UTF8')))"
                )
            )
            assert (
                c.scalar(
                    text(
                        "SELECT public.account_test_row_delete_allowed('public.billing_records'::regclass,'{}'::jsonb)"
                    )
                )
                is True
            )
            with pytest.raises(DBAPIError, match="lock timeout"):
                with engine.begin() as competing:
                    competing.execute(text("SET LOCAL lock_timeout='100ms'"))
                    competing.execute(
                        text("UPDATE account_test_data_policy SET enabled=false")
                    )
            c.execute(
                text(
                    "DELETE FROM account_test_delete_capabilities WHERE transaction_id=pg_current_xact_id()::text"
                )
            )
        with engine.begin() as c:
            c.execute(text("UPDATE account_test_data_policy SET enabled=false"))
            assert c.scalar(text("SELECT public.account_test_data_enabled()")) is False
    finally:
        engine.dispose()


def test_policy_change_in_progress_refuses_old_test_snapshot_without_waiting(
    migrated_postgres,
):
    engine = create_engine(migrated_postgres)
    try:
        with engine.begin() as c:
            enable_test_policy(c)
        with engine.begin() as changing:
            changing.execute(text("UPDATE account_test_data_policy SET enabled=false"))
            with pytest.raises(DBAPIError, match="could not obtain lock"):
                with engine.begin() as c:
                    c.execute(text("SELECT public.account_lock_test_data_policy()"))
        with engine.begin() as c:
            assert c.scalar(text("SELECT public.account_test_data_enabled()")) is False
    finally:
        engine.dispose()


@pytest.mark.parametrize("metadata", ["[]", '{"actor_sub":"another-payer"}'])
def test_ambiguous_native_payer_ownership_is_not_waived_in_test(
    migrated_postgres, metadata
):
    from controlplane_db.test_retention import (
        purge_test_finances,
        TestRetentionUnavailable,
    )

    engine = create_engine(migrated_postgres)

    def ambiguous(c, subject, user, payment, tenant):
        c.execute(
            text("UPDATE billing_records SET metadata=CAST(:m AS jsonb) WHERE id=:p"),
            {"m": metadata, "p": payment},
        )

    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(c, before_close=ambiguous)
            enable_test_policy(c)
        with pytest.raises(TestRetentionUnavailable, match="native payer ownership"):
            with engine.begin() as c:
                purge_test_finances(c, subject, at)
        with engine.begin() as c:
            assert (
                c.scalar(
                    text("SELECT count(*) FROM billing_records WHERE id=:p"),
                    {"p": payment},
                )
                == 1
            )
    finally:
        engine.dispose()


def test_retired_creator_cannot_delete_company_finances_or_claim_an_empty_scope(
    migrated_postgres,
):
    import uuid, json
    from controlplane_db.test_retention import purge_test_finances

    engine = create_engine(migrated_postgres)
    company_payment = uuid.uuid4()

    def company(c, subject, user, payment, tenant):
        c.execute(
            text(
                "INSERT INTO billing_records(id,scope,actor,user_id,payment_type,currency,amount,status,metadata) VALUES(:p,'invoice','tenant',:u,'stripe_invoice','usd',100,'pending',CAST(:m AS jsonb))"
            ),
            {"p": company_payment, "u": user, "m": json.dumps({"actor_sub": subject})},
        )

    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(c, before_close=company)
            enable_test_policy(c)
        with engine.begin() as c:
            receipt = purge_test_finances(c, subject, at)
            assert receipt["roots_complete"] is True and receipt["complete"] is False
            assert receipt["deleted"] == 1 and receipt["remaining"] > 0
            assert (
                c.scalar(
                    text("SELECT count(*) FROM billing_records WHERE id=:p"),
                    {"p": company_payment},
                )
                == 1
            )
    finally:
        engine.dispose()


def test_billing_batch_cannot_orphan_a_skipped_hashed_payer_risk_row(migrated_postgres):
    import hashlib
    from controlplane_db.test_retention import purge_test_finances

    engine = create_engine(migrated_postgres)
    keys = []

    def risk(c, subject, user, payment, tenant):
        key = hashlib.sha256(subject.encode()).hexdigest()
        keys.append(key)
        c.execute(
            text(
                "INSERT INTO payer_mismatch_accounts(account_key,day) VALUES(:k,CURRENT_DATE)"
            ),
            {"k": key},
        )

    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(c, before_close=risk)
            enable_test_policy(c)
        with engine.begin() as c:
            receipt = purge_test_finances(c, subject, at, limit=1)
            assert receipt["complete"] is False and receipt["roots_complete"] is False
            assert receipt["tables"] == {"billing_records": 1}
            assert (
                c.scalar(
                    text(
                        "SELECT count(*) FROM account_financial_source_bindings WHERE subject=:s AND kind='payer_mismatch_accounts'"
                    ),
                    {"s": subject},
                )
                == 1
            )
            assert (
                c.scalar(
                    text(
                        "SELECT count(*) FROM payer_mismatch_accounts WHERE account_key=:k"
                    ),
                    {"k": keys[0]},
                )
                == 1
            )
        with engine.begin() as c:
            receipt = purge_test_finances(c, subject, at, limit=1)
            assert receipt["complete"] is True
            assert receipt["tables"] == {"payer_mismatch_accounts": 1}
            assert (
                c.scalar(
                    text(
                        "SELECT count(*) FROM payer_mismatch_accounts WHERE account_key=:k"
                    ),
                    {"k": keys[0]},
                )
                == 0
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize("chain,allowed", [(8453, False), (84532, True)])
def test_legacy_native_chain_discriminator_protects_mainnet_rows(
    migrated_postgres, chain, allowed
):
    import uuid
    from controlplane_db.test_retention import (
        purge_test_finances,
        TestRetentionUnavailable,
    )

    engine = create_engine(migrated_postgres)

    def legacy(c, subject, user, payment, tenant):
        # Model an administrator-restored historical native table. The retired
        # custody chain is normally absent, but it must not bypass the network
        # boundary if encountered during TEST cleanup. Its native discriminator
        # is chain_id, not a livemode field.
        c.execute(
            text("""CREATE TABLE usdc_deposit_addresses(
          tenant_id uuid NOT NULL REFERENCES tenants(id),user_id uuid NOT NULL REFERENCES users(id),
          chain_id integer NOT NULL CHECK(chain_id IN(8453,84532)),address varchar(42) NOT NULL,
          PRIMARY KEY(tenant_id,user_id,chain_id))""")
        )
        c.execute(
            text(
                "CREATE TRIGGER legacy_immutable BEFORE DELETE ON usdc_deposit_addresses FOR EACH ROW EXECUTE FUNCTION public.connect_recipient_immutable()"
            )
        )
        c.execute(
            text("INSERT INTO usdc_deposit_addresses VALUES(:t,:u,:chain,:address)"),
            {"t": tenant, "u": user, "chain": chain, "address": "0x" + "a" * 40},
        )

    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(
                c, tenant=uuid.uuid4(), before_close=legacy
            )
            enable_test_policy(c)
        if allowed:
            with engine.begin() as c:
                receipt = purge_test_finances(c, subject, at)
                assert (
                    receipt["complete"] is True
                    and receipt["tables"]["usdc_deposit_addresses"] == 1
                )
        else:
            with pytest.raises(TestRetentionUnavailable, match="provider network"):
                with engine.begin() as c:
                    purge_test_finances(c, subject, at)
        with engine.begin() as c:
            assert c.scalar(text("SELECT count(*) FROM usdc_deposit_addresses")) == (
                0 if allowed else 1
            )
            assert (
                c.scalar(text("SELECT count(*) FROM account_test_delete_capabilities"))
                == 0
            )
    finally:
        engine.dispose()


def test_directory_uuid_from_another_tenant_grants_no_financial_erasure(
    migrated_postgres,
):
    import uuid
    from controlplane_db.test_retention import purge_test_finances

    engine = create_engine(migrated_postgres)
    foreign = uuid.uuid4()
    other_tenant = uuid.uuid4()
    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(c, tenant=uuid.uuid4())
            c.execute(
                text("INSERT INTO tenants(id,name,is_active) VALUES(:t,:n,true)"),
                {"t": other_tenant, "n": str(other_tenant)},
            )
            c.execute(
                text(
                    "INSERT INTO billing_records(id,tenant_id,scope,actor,user_id,payment_type,currency,amount,status,metadata) VALUES(:p,:t,'lease','user',:u,'card','usd',100,'pending','{}'::jsonb)"
                ),
                {"p": foreign, "t": other_tenant, "u": user},
            )
            enable_test_policy(c)
        with engine.begin() as c:
            receipt = purge_test_finances(c, subject, at)
            assert receipt["complete"] is False and receipt["tables"] == {
                "billing_records": 1
            }
            assert (
                c.scalar(
                    text("SELECT count(*) FROM billing_records WHERE id=:p"),
                    {"p": foreign},
                )
                == 1
            )
    finally:
        engine.dispose()


def test_opaque_pricing_org_alias_is_not_customer_ownership(migrated_postgres):
    import uuid
    from controlplane_db.test_retention import purge_test_finances

    engine = create_engine(migrated_postgres)
    order = uuid.uuid4().hex

    def company_order(c, subject, user, payment, tenant):
        c.execute(
            text(
                "INSERT INTO hypermesh_pricing_pools(pool_id,tenant_id,class_id,region,kind,created_at) VALUES('test@region',:t,'test','region','P1',now())"
            ),
            {"t": tenant},
        )
        c.execute(
            text(
                "INSERT INTO hypermesh_orders(order_id,tenant_id,org_id,pool_id,rungs,tip_cents,hours,status,created_at) VALUES(:o,:t,:s,'test@region','[]'::jsonb,0,1,'open',now())"
            ),
            {"o": order, "t": tenant, "s": subject},
        )

    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(
                c, tenant=uuid.uuid4(), before_close=company_order
            )
            enable_test_policy(c)
        with engine.begin() as c:
            receipt = purge_test_finances(c, subject, at)
            assert receipt["complete"] is False and receipt["tables"] == {
                "billing_records": 1
            }
            assert (
                c.scalar(
                    text("SELECT count(*) FROM hypermesh_orders WHERE order_id=:o"),
                    {"o": order},
                )
                == 1
            )
    finally:
        engine.dispose()
