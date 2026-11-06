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
            "INSERT INTO account_test_delete_capabilities(transaction_id,relation,row_digest) VALUES(pg_current_xact_id()::text,0,decode('00','hex'))",
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
                        "INSERT INTO account_test_delete_capabilities(transaction_id,relation,row_digest) VALUES(pg_current_xact_id()::text,'public.billing_records'::regclass,sha256(convert_to('{}'::jsonb::text,'UTF8')))"
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
            text(
                """INSERT INTO billing_tax_orders(revision_id,tenant_id,billing_record_id,seller_id,supply,fee_payer,policy_version,tax_code,subtotal_cents,country,state,postal_code,city,line1,line2)
          VALUES(:tax,:t,:p,:host,'owned','host','EXAMPLE-test','txcd_00000000',1234,'US','CA','00000','Test City','Fixture','')"""
            ),
            params,
        )
        c.execute(
            text(
                "INSERT INTO billing_tax_calculations(revision_id,tenant_id,attempted_at) VALUES(:tax,:t,now())"
            ),
            params,
        )
        c.execute(
            text(
                """INSERT INTO hypermesh_leases(id,tenant_id,kind,status,renter_user_id,class_id,host_org_id,billing_record_id,reserved_hours,created_at,token_count,loaded_hours,purpose)
          VALUES(:lease,:t,'p1_hardware','active',:u,'test-class',:host,:p,1,now(),0,0,'renter')"""
            ),
            params,
        )
        c.execute(
            text(
                """INSERT INTO hypermesh_payouts(lease_id,tenant_id,host_org_id,host_pubkey,kind,gross_cents,stripe_cut_cents,platform_take_cents,take_bps,net_cents,net_usdc_atoms)
          VALUES(:lease,:t,:host,'test-host','p1_hardware',1234,0,234,1900,1000,10000000)"""
            ),
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
                    text(
                        """SELECT public.account_issue_financial_transition(:s,:at,NULL,ARRAY[CAST(:s AS text)],
                  'billing','billing_records',b.id::text,to_jsonb(b),NULL,NULL) FROM billing_records b WHERE b.id=:p"""
                    ),
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
                    "INSERT INTO account_test_delete_capabilities(transaction_id,relation,row_digest) VALUES(pg_current_xact_id()::text,'public.billing_records'::regclass,sha256(convert_to('{}'::jsonb::text,'UTF8')))"
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
            text(
                """CREATE TABLE usdc_deposit_addresses(
          tenant_id uuid NOT NULL REFERENCES tenants(id),user_id uuid NOT NULL REFERENCES users(id),
          chain_id integer NOT NULL CHECK(chain_id IN(8453,84532)),address varchar(42) NOT NULL,
          PRIMARY KEY(tenant_id,user_id,chain_id))"""
            )
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


def test_ineligible_tenant_rows_cannot_starve_a_bounded_financial_batch(
    migrated_postgres,
):
    import uuid
    from controlplane_db.test_retention import purge_test_finances

    engine = create_engine(migrated_postgres)
    foreign = [uuid.uuid4(), uuid.uuid4()]
    other_tenant = uuid.uuid4()

    def reorder(c, subject, user, payment, tenant):
        c.execute(
            text("INSERT INTO tenants(id,name,is_active) VALUES(:t,:n,true)"),
            {"t": other_tenant, "n": str(other_tenant)},
        )
        for identifier in foreign:
            c.execute(
                text(
                    "INSERT INTO billing_records(id,tenant_id,scope,actor,user_id,payment_type,currency,amount,status,metadata) VALUES(:p,:t,'lease','user',:u,'card','usd',100,'pending','{}'::jsonb)"
                ),
                {"p": identifier, "t": other_tenant, "u": user},
            )
        # Put the eligible live tuple after both unrelated rows in the heap.
        c.execute(
            text("UPDATE billing_records SET amount=amount WHERE id=:p"), {"p": payment}
        )

    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(
                c, tenant=uuid.uuid4(), before_close=reorder
            )
            enable_test_policy(c)
        with engine.begin() as c:
            receipt = purge_test_finances(c, subject, at, limit=1)
            assert receipt["tables"] == {"billing_records": 1}
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
                        "SELECT count(*) FROM billing_records WHERE id=ANY(CAST(:ids AS uuid[]))"
                    ),
                    {"ids": foreign},
                )
                == 2
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "livemode,original_recipient", [(False, True), (True, True), (False, False)]
)
def test_connect_grants_and_results_require_the_original_sandbox_recipient(
    migrated_postgres, livemode, original_recipient
):
    import uuid
    from controlplane_db.test_retention import (
        purge_test_finances,
        TestRetentionUnavailable,
    )

    engine = create_engine(migrated_postgres)
    grant, host, attempt = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    def connect(c, subject, user, payment, tenant):
        c.execute(
            text(
                "INSERT INTO connect_recipient_accounts(tenant_id,host_org_id,livemode,live_approval_reference,attempt_id,attempted_at,legal_type,country,state,stripe_account_id,creation_status,initiated_by_sub) VALUES(:t,:h,:live,:approval,:a,transaction_timestamp(),'individual','US','WA','acct_TestOwner','bound',:initiator)"
            ),
            {
                "t": tenant,
                "h": host,
                "live": livemode,
                "approval": "fixture-live-approval" if livemode else None,
                "a": attempt,
                "initiator": str(uuid.uuid4()),
            },
        )
        c.execute(
            text(
                "UPDATE connect_access_states SET policy='embedded-api/v1',epoch=epoch+1 WHERE tenant_id=:t AND host_org_id=:h"
            ),
            {"t": tenant, "h": host},
        )
        c.execute(
            text(
                "INSERT INTO connect_access_grants(id,tenant_id,host_org_id,enrollment_attempt_id,platform_id,account_id,owner_sub,member_id,issuer_session,purpose,policy,policy_hash,epoch,parameters,idempotency_key,created_at) VALUES(:g,:t,:h,:a,'acct_TestPlatform',:account,:s,'fixture-member','fixture-session','view','embedded-api/v1',repeat('a',64),2,'{}'::jsonb,:key,transaction_timestamp())"
            ),
            {
                "g": grant,
                "t": tenant,
                "h": host,
                "a": attempt,
                "s": subject,
                "key": str(grant),
                "account": (
                    "acct_TestOwner" if original_recipient else "acct_DifferentOwner"
                ),
            },
        )
        c.execute(
            text(
                "INSERT INTO connect_access_results(grant_id,tenant_id,expires_at,observed_at,request_id,permissions) VALUES(:g,:t,now()+interval '1 hour',now(),'req_fixture','{}'::jsonb)"
            ),
            {"g": grant, "t": tenant},
        )

    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(
                c, tenant=uuid.uuid4(), before_close=connect
            )
            enable_test_policy(c)
        refused = livemode or not original_recipient
        if refused:
            with pytest.raises(TestRetentionUnavailable, match="Connect ancestry"):
                with engine.begin() as c:
                    purge_test_finances(c, subject, at)
        else:
            with engine.begin() as c:
                receipt = purge_test_finances(c, subject, at)
                assert receipt["complete"] is True
                assert receipt["tables"] == {
                    "billing_records": 1,
                    "connect_access_grants": 1,
                    "connect_access_results": 1,
                }
        with engine.begin() as c:
            assert c.scalar(
                text("SELECT count(*) FROM connect_access_grants WHERE id=:g"),
                {"g": grant},
            ) == int(refused)
            assert c.scalar(
                text("SELECT count(*) FROM connect_access_results WHERE grant_id=:g"),
                {"g": grant},
            ) == int(refused)
            assert c.scalar(
                text("SELECT count(*) FROM billing_records WHERE id=:p"), {"p": payment}
            ) == int(refused)
            assert (
                c.scalar(
                    text(
                        "SELECT count(*) FROM connect_recipient_accounts WHERE host_org_id=:h"
                    ),
                    {"h": host},
                )
                == 1
            )
            assert (
                c.scalar(text("SELECT count(*) FROM account_test_delete_capabilities"))
                == 0
            )
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "scenario",
    ["sandbox", "live_connect", "mainnet", "physical_child", "shared_billing"],
)
def test_restricted_coordinator_cannot_forge_or_write_financial_authority(
    migrated_postgres, scenario
):
    import uuid
    from controlplane_db.test_retention import financial_tables, purge_test_finances

    engine = create_engine(migrated_postgres)
    role = "test_coordinator_" + uuid.uuid4().hex
    host, attempt, grant, address = [uuid.uuid4() for _ in range(4)]

    def connect(c, subject, user, payment, tenant):
        if scenario == "shared_billing":
            former_user, former_subject = uuid.uuid4(), str(uuid.uuid4())
            c.execute(
                text(
                    "INSERT INTO users(id,tenant_id,first_name,last_name,email,gender,is_active,keycloak_sub) VALUES(:u,:t,'Former','Payer',:email,'unspecified',true,:s)"
                ),
                {
                    "u": former_user,
                    "t": tenant,
                    "email": former_subject + "@example.invalid",
                    "s": former_subject,
                },
            )
            c.execute(
                text(
                    "INSERT INTO account_lifecycles(subject,requested_at,requested_by,source,state,retry_at,financial_hold,effects) VALUES(:s,now(),:s,'self_service','closing',now(),false,'{}'::jsonb)"
                ),
                {"s": former_subject},
            )
            # Real billing updates retain both original and current parties.
            for payer, actor in [(former_user, former_subject), (user, subject)]:
                c.execute(
                    text(
                        "UPDATE billing_records SET user_id=:u, metadata=jsonb_build_object('actor_sub',CAST(:s AS text)) WHERE id=:p"
                    ),
                    {"u": payer, "s": actor, "p": payment},
                )
            return
        if scenario != "live_connect":
            return
        c.execute(
            text(
                "INSERT INTO connect_recipient_accounts(tenant_id,host_org_id,livemode,live_approval_reference,attempt_id,attempted_at,legal_type,country,state,stripe_account_id,creation_status,initiated_by_sub) VALUES(:t,:h,true,'fixture-live',:a,now(),'individual','US','WA','acct_RestrictedLive','bound',:initiator)"
            ),
            {"t": tenant, "h": host, "a": attempt, "initiator": str(uuid.uuid4())},
        )
        c.execute(
            text(
                "INSERT INTO connect_access_grants(id,tenant_id,host_org_id,enrollment_attempt_id,platform_id,account_id,owner_sub,member_id,issuer_session,purpose,policy,policy_hash,epoch,parameters,idempotency_key,created_at) VALUES(:g,:t,:h,:a,'acct_Platform','acct_RestrictedLive',:s,'member','session','view','embedded-api/v1',repeat('a',64),1,'{}'::jsonb,:key,now())"
            ),
            {
                "g": grant,
                "t": tenant,
                "h": host,
                "a": attempt,
                "s": subject,
                "key": str(grant),
            },
        )

    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(
                c,
                tenant=uuid.uuid4() if scenario == "live_connect" else None,
                before_close=connect,
            )
            enable_test_policy(c)
            if scenario == "mainnet":
                c.execute(
                    text(
                        "CREATE TABLE usdc_deposit_addresses(id uuid PRIMARY KEY,user_id uuid NOT NULL,chain_id integer NOT NULL)"
                    )
                )
                c.execute(
                    text("INSERT INTO usdc_deposit_addresses VALUES(:id,:u,8453)"),
                    {"id": address, "u": user},
                )
            if scenario == "physical_child":
                c.execute(
                    text(
                        "CREATE TABLE physical_owner_child(id uuid PRIMARY KEY,billing_id uuid REFERENCES billing_records(id) ON DELETE CASCADE)"
                    )
                )
                c.execute(
                    text("INSERT INTO physical_owner_child VALUES(:id,:p)"),
                    {"id": uuid.uuid4(), "p": payment},
                )
            c.exec_driver_sql(
                f"CREATE ROLE {role} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION BYPASSRLS"
            )
            tables = list(financial_tables()) + [
                "account_lifecycles",
                "account_lifecycle_scopes",
                "account_financial_source_bindings",
                "users",
                "identity_retirements",
            ]
            for name in tables:
                if (
                    c.scalar(text("SELECT to_regclass(:n)"), {"n": "public." + name})
                    is not None
                ):
                    c.exec_driver_sql(f'GRANT SELECT ON public."{name}" TO {role}')
            for signature in (
                "account_test_data_enabled()",
                "account_lock_test_data_policy()",
                "account_require_financial_inventory(text,timestamptz)",
                "account_lock_financial_inventory(text,timestamptz,uuid)",
                "hypermesh_financial_parties(text,jsonb)",
                "account_lock_test_financial_sources(text,timestamptz)",
                "account_stage_test_delete(text,timestamptz,oid,text,oid,text)",
                "account_delete_test_financial_row(text,timestamptz,oid,text)",
                "account_clear_test_delete_capabilities()",
                "account_reconcile_test_financial_bindings(text,timestamptz)",
            ):
                c.exec_driver_sql(
                    f"GRANT EXECUTE ON FUNCTION public.{signature} TO {role}"
                )
            table = (
                "connect_access_grants"
                if scenario == "live_connect"
                else (
                    "usdc_deposit_addresses"
                    if scenario == "mainnet"
                    else "billing_records"
                )
            )
            identifier = (
                grant
                if scenario == "live_connect"
                else (address if scenario == "mainnet" else payment)
            )
            oid, tid = c.execute(
                text(f"SELECT tableoid,ctid::text FROM public.{table} WHERE id=:id"),
                {"id": identifier},
            ).one()
        for command in (
            "INSERT INTO account_test_delete_capabilities(transaction_id,relation,row_digest) SELECT pg_current_xact_id()::text,1,decode('00','hex')",
            "DELETE FROM account_test_delete_capabilities WHERE false",
            "DELETE FROM account_financial_source_bindings WHERE false",
            f"DELETE FROM {table} WHERE false",
        ):
            with pytest.raises(DBAPIError, match="permission denied"):
                with engine.begin() as c:
                    c.exec_driver_sql(f"SET LOCAL ROLE {role}")
                    c.execute(text(command))
        if scenario == "sandbox":
            with pytest.raises(DBAPIError, match="capability required"):
                with engine.begin() as c:
                    c.exec_driver_sql(f"SET LOCAL ROLE {role}")
                    c.execute(
                        text(
                            "SELECT public.account_delete_test_financial_row(:s,:at,CAST(:r AS oid),:tid)"
                        ),
                        {"s": subject, "at": at, "r": oid, "tid": tid},
                    )
            with engine.begin() as c:
                c.exec_driver_sql(f"SET LOCAL ROLE {role}")
                assert purge_test_finances(c, subject, at)["complete"] is True
        elif scenario == "physical_child":
            with pytest.raises(DBAPIError, match="dependent rows"):
                with engine.begin() as c:
                    c.exec_driver_sql(f"SET LOCAL ROLE {role}")
                    c.execute(
                        text(
                            "SELECT public.account_stage_test_delete(:s,:at,CAST(:r AS oid),:tid,NULL,NULL)"
                        ),
                        {"s": subject, "at": at, "r": oid, "tid": tid},
                    )
                    c.execute(
                        text(
                            "SELECT public.account_delete_test_financial_row(:s,:at,CAST(:r AS oid),:tid)"
                        ),
                        {"s": subject, "at": at, "r": oid, "tid": tid},
                    )
            with engine.begin() as c:
                assert c.scalar(text("SELECT count(*) FROM physical_owner_child")) == 1
                assert (
                    c.scalar(
                        text("SELECT count(*) FROM billing_records WHERE id=:p"),
                        {"p": payment},
                    )
                    == 1
                )
        else:
            if scenario == "shared_billing":
                from controlplane_db.test_retention import TestRetentionUnavailable

                with pytest.raises(
                    TestRetentionUnavailable, match="Shared native billing"
                ):
                    with engine.begin() as c:
                        c.exec_driver_sql(f"SET LOCAL ROLE {role}")
                        purge_test_finances(c, subject, at)
            with pytest.raises(
                DBAPIError,
                match=(
                    "Shared native billing"
                    if scenario == "shared_billing"
                    else "Live or"
                ),
            ):
                with engine.begin() as c:
                    c.exec_driver_sql(f"SET LOCAL ROLE {role}")
                    c.execute(
                        text(
                            "SELECT public.account_stage_test_delete(:s,:at,CAST(:r AS oid),:tid,NULL,NULL)"
                        ),
                        {"s": subject, "at": at, "r": oid, "tid": tid},
                    )
            with engine.begin() as c:
                assert (
                    c.scalar(
                        text(f"SELECT count(*) FROM public.{table} WHERE id=:id"),
                        {"id": identifier},
                    )
                    == 1
                )
                assert (
                    c.scalar(
                        text("SELECT count(*) FROM account_test_delete_capabilities")
                    )
                    == 0
                )
    finally:
        with engine.begin() as c:
            c.exec_driver_sql(f"DROP OWNED BY {role}")
            c.exec_driver_sql(f"DROP ROLE IF EXISTS {role}")
        engine.dispose()


@pytest.mark.parametrize("ownership", ["same", "foreign_purchase", "foreign_entitlement"])
def test_marketplace_dependencies_require_the_original_scoped_buyer(migrated_postgres, ownership):
    import uuid
    from controlplane_db.test_retention import purge_test_finances, TestRetentionUnavailable

    engine = create_engine(migrated_postgres)
    tenant, buyer, listing, purchase, entitlement = [uuid.uuid4() for _ in range(5)]
    def marketplace(c, subject, user, payment, tenant):
        c.execute(text("INSERT INTO users(id,tenant_id,first_name,last_name,email,gender,is_active,keycloak_sub) VALUES(:u,:t,'Other','Buyer',:email,'unspecified',true,:s)"),
                  {"u":buyer,"t":tenant,"email":str(buyer)+"@example.invalid","s":str(buyer)})
        c.execute(text("INSERT INTO marketplace_listings(id,tenant_id,seller_id,title,description,listing_type,price_type,is_public) VALUES(:l,:t,:u,'Fixture','Fixture','agent','fixed',false)"),
                  {"l":listing,"t":tenant,"u":user})
        c.execute(text("INSERT INTO marketplace_purchases(id,tenant_id,listing_id,buyer_id,status,billing_record_id) VALUES(:p,:t,:l,:u,'paid',:b)"),
                  {"p":purchase,"t":tenant,"l":listing,"u":buyer if ownership=='foreign_purchase' else user,"b":payment})
        c.execute(text("INSERT INTO ai_agent_entitlements(id,tenant_id,buyer_id,purchase_id,listing_id,license_key_sha256) VALUES(:e,:t,:u,:p,:l,repeat('a',64))"),
                  {"e":entitlement,"t":tenant,"u":user if ownership=='same' else buyer,"p":purchase,"l":listing})
    try:
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(c, tenant=tenant, before_close=marketplace)
            enable_test_policy(c)
        if ownership=='same':
            with engine.begin() as c:
                receipt = purge_test_finances(c,subject,at)
                assert receipt['tables']=={'billing_records':1,'marketplace_purchases':1,'ai_agent_entitlements':1}
        else:
            with pytest.raises(TestRetentionUnavailable,match='Foreign native TEST customer'):
                with engine.begin() as c:
                    purge_test_finances(c,subject,at)
            # Bypass the Python planner: the native issuer independently refuses
            # the foreign buyer even with an authorized exact parent capability.
            with pytest.raises(DBAPIError,match='Foreign native TEST customer'):
                with engine.begin() as c:
                    parent_oid=parent_tid=None
                    for table, identifier in [('billing_records',payment),('marketplace_purchases',purchase),('ai_agent_entitlements',entitlement)]:
                        oid,tid=c.execute(text(f'SELECT tableoid,ctid::text FROM public.{table} WHERE id=:id'),{'id':identifier}).one()
                        c.execute(text('SELECT public.account_stage_test_delete(:s,:at,CAST(:r AS oid),:tid,CAST(:parent AS oid),:parent_tid)'),
                                  {'s':subject,'at':at,'r':oid,'tid':tid,'parent':parent_oid,'parent_tid':parent_tid})
                        parent_oid,parent_tid=oid,tid
            with engine.begin() as c:
                for table, identifier in [('billing_records',payment),('marketplace_purchases',purchase),('ai_agent_entitlements',entitlement)]:
                    assert c.scalar(text(f'SELECT count(*) FROM public.{table} WHERE id=:id'),{'id':identifier})==1
                assert c.scalar(text('SELECT count(*) FROM account_test_delete_capabilities'))==0
    finally:
        engine.dispose()


@pytest.mark.parametrize("livemode", [None,False,True])
@pytest.mark.parametrize("provider_field", ["stripe_customer_id","stripe_session_id","stripe_subscription_id","metadata"])
def test_stripe_billing_requires_immutable_sandbox_provenance(migrated_postgres,livemode,provider_field):
    from controlplane_db.test_retention import purge_test_finances
    engine=create_engine(migrated_postgres)
    try:
        with engine.begin() as c:
            subject,at,user,payment=seed_closed_payer(c)
            enable_test_policy(c)
            if provider_field=='metadata':
                c.execute(text("UPDATE billing_records SET metadata=metadata||'{\"stripe_payment_intent_id\":\"pi_fixture\"}'::jsonb WHERE id=:p"),{'p':payment})
            else:
                c.execute(text(f"UPDATE billing_records SET {provider_field}='provider_fixture' WHERE id=:p"),{'p':payment})
            c.execute(text('UPDATE billing_records SET stripe_livemode=:mode WHERE id=:p'),{'mode':livemode,'p':payment})
        if livemode is False:
            with engine.begin() as c:
                assert purge_test_finances(c,subject,at)['tables']=={'billing_records':1}
        else:
            with pytest.raises(DBAPIError,match='Immutable Stripe sandbox provenance'):
                with engine.begin() as c:
                    oid,tid=c.execute(text('SELECT tableoid,ctid::text FROM billing_records WHERE id=:p'),{'p':payment}).one()
                    c.execute(text('SELECT public.account_stage_test_delete(:s,:at,CAST(:r AS oid),:tid,NULL,NULL)'),{'s':subject,'at':at,'r':oid,'tid':tid})
            with engine.begin() as c:
                assert c.scalar(text('SELECT count(*) FROM billing_records WHERE id=:p'),{'p':payment})==1
        if livemode is True:
            for replacement in [None,False]:
                with pytest.raises(DBAPIError,match='mode is immutable'):
                    with engine.begin() as c:
                        c.execute(text('UPDATE billing_records SET stripe_livemode=:mode WHERE id=:p'),{'mode':replacement,'p':payment})
    finally:
        engine.dispose()


@pytest.mark.parametrize('field', ['stripe_customer_id', 'stripe_subscription_id', 'stripe_session_id'])
def test_stripe_billing_without_immutable_mode_is_retained(migrated_postgres, field):
    from controlplane_db.test_retention import purge_test_finances
    engine = create_engine(migrated_postgres)
    try:
        def provider(c, subject, user, payment, tenant):
            c.execute(text(f"UPDATE billing_records SET {field}=:v WHERE id=:p"),
                      {'v': 'provider_opaque_identifier', 'p': payment})
        with engine.begin() as c:
            subject, at, user, payment = seed_closed_payer(c, before_close=provider)
            c.execute(text("INSERT INTO account_test_data_policy(singleton,database_oid,database_name,enabled) VALUES(true,(SELECT oid FROM pg_database WHERE datname=current_database()),current_database(),true)"))
        with pytest.raises(DBAPIError, match='Immutable Stripe sandbox provenance'):
            with engine.begin() as c:
                purge_test_finances(c, subject, at)
        with engine.begin() as c:
            assert c.scalar(text('SELECT count(*) FROM billing_records WHERE id=:p'), {'p':payment}) == 1
            assert c.scalar(text('SELECT count(*) FROM account_test_delete_capabilities')) == 0
    finally:
        engine.dispose()


@pytest.mark.parametrize('data', [
    {'stripe_customer_id': 'cus_live'},
    {'stripe_subscription_id': 'sub_live'},
    {'stripe_session_id': 'cs_live'},
    {'payment_type': 'stripe_invoice'},
    {'metadata': {'stripe_session_id': 'cs_live', 'livemode': False}},
])
def test_database_guard_refuses_unproven_stripe_mode(migrated_postgres, data):
    import json
    engine = create_engine(migrated_postgres)
    try:
        with pytest.raises(DBAPIError, match='Immutable Stripe sandbox provenance'):
            with engine.begin() as c:
                c.execute(text("SELECT public.account_test_check_row('billing_records',CAST(:d AS jsonb))"), {'d':json.dumps(data)})
    finally:
        engine.dispose()


@pytest.mark.parametrize('metadata', [
    {'payment_rail':'stripe_stablecoin'},
    {'pending_refund':{'stripe_refund_id':'re_live'}},
    {'history':[{'nested':{'stripe_session_id':'cs_live'}}]},
])
@pytest.mark.parametrize('mode', [None, True, False])
def test_nested_stripe_markers_require_immutable_mode(migrated_postgres, metadata, mode):
    import json
    engine=create_engine(migrated_postgres)
    try:
        def check():
            with engine.begin() as c:
                c.execute(text("SELECT public.account_test_check_row('billing_records',CAST(:d AS jsonb))"),
                          {'d':json.dumps({'metadata':metadata,'stripe_livemode':mode})})
        if mode is False: check()
        else:
            with pytest.raises(DBAPIError,match='Immutable Stripe sandbox provenance'): check()
    finally: engine.dispose()


@pytest.mark.parametrize('parent', ['missing','unknown','live','wrong_session','wrong_tenant','sandbox'])
def test_stripe_lease_requires_matching_original_sandbox_billing(migrated_postgres,parent):
    import json,uuid
    engine=create_engine(migrated_postgres)
    try:
        with engine.begin() as c:
            _,_,_,payment=seed_closed_payer(c)
            c.execute(text("UPDATE billing_records SET stripe_session_id='cs_original',stripe_livemode=:mode WHERE id=:id"),
                      {'mode':None if parent=='unknown' else parent=='live','id':payment})
        data={'stripe_session_id':'cs_other' if parent=='wrong_session' else 'cs_original',
              'billing_record_id':None if parent=='missing' else str(payment),
              'tenant_id':str(uuid.uuid4()) if parent=='wrong_tenant' else None}
        def check():
            with engine.begin() as c:
                c.execute(text("SELECT public.account_test_check_row('hypermesh_leases',CAST(:d AS jsonb))"),{'d':json.dumps(data)})
        if parent=='sandbox': check()
        else:
            with pytest.raises(DBAPIError,match='Original Stripe lease sandbox provenance'):check()
    finally:engine.dispose()
