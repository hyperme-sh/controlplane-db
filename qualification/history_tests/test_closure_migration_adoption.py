"""Upgrade both reviewed histories without replacing existing migration bytes."""
import os
import uuid
from contextlib import contextmanager

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from controlplane_db import migrations


@contextmanager
def disposable_database():
    value = os.environ.get('TEST_DATABASE_URL')
    if not value:
        pytest.skip('requires owned disposable PostgreSQL TEST_DATABASE_URL')
    base = make_url(value).set(drivername='postgresql+psycopg')
    name = 'closure_adoption_' + uuid.uuid4().hex
    admin = create_engine(base, isolation_level='AUTOCOMMIT')
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        yield base.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


@pytest.mark.parametrize('previous', [None, 'platform_0057_share_lookup', 'platform_0078_fin_empty'])
def test_upgrade_reconciles_hardening_and_closure_and_preserves_worker_preflight(previous):
    with disposable_database() as url:
        engine = create_engine(url)
        try:
            if previous:
                with engine.begin() as connection:
                    command.upgrade(migrations._config(migrations._ROOT, 'platform', connection), previous)
                    connection.execute(text("INSERT INTO tenants(id,name,is_active) VALUES(:id,'retained',true)"), {'id': uuid.uuid4()})
            migrations.upgrade(url)
            assert migrations.current_heads(url) == migrations.chain_heads()
            assert migrations.chain_heads()['platform'] == 'platform_0085_stripe_merge'
            with engine.begin() as connection:
                connection.execute(text('SELECT public.account_check_closure_worker_installation()'))
                assert connection.scalar(text("SELECT to_regclass('public.identity_retirements') IS NOT NULL"))
                assert connection.scalar(text("SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname='account_finish_source_free_closure'")) == 1
                settings = connection.scalar(text("SELECT proconfig FROM pg_proc WHERE oid='public.sociacl_share_lookup_by_hash(varchar)'::regprocedure"))
                assert any('pg_temp' in item for item in settings)
                # PUBLIC execution remains revoked after both branches are applied.
                assert not connection.scalar(text("SELECT EXISTS(SELECT 1 FROM pg_proc p, LATERAL aclexplode(COALESCE(p.proacl,acldefault('f',p.proowner))) a WHERE p.oid='public.sociacl_share_lookup_by_hash(varchar)'::regprocedure AND a.grantee=0 AND a.privilege_type='EXECUTE')"))
                if previous:
                    assert connection.scalar(text("SELECT count(*) FROM tenants WHERE name='retained'")) == 1
            # A repeat is a true no-op over the same database, not a new template.
            migrations.upgrade(url)
            assert migrations.current_heads(url) == migrations.chain_heads()
        finally:
            engine.dispose()


@pytest.mark.parametrize('previous', ['hypermesh_0070_violation_ops', 'hypermesh_0086_fin_state'])
def test_hypermesh_lab_and_closure_histories_converge_without_rewriting(previous):
    with disposable_database() as url:
        migrations.upgrade(url, chains=['platform', 'events'])
        engine = create_engine(url)
        try:
            with engine.begin() as connection:
                command.upgrade(migrations._config(migrations._ROOT, 'hypermesh', connection), previous)
                identifier = uuid.uuid4()
                connection.execute(text("INSERT INTO tenants(id,name,is_active) VALUES(:id,'retained-hypermesh',true)"), {'id': identifier})
                if previous == 'hypermesh_0070_violation_ops':
                    connection.execute(text('INSERT INTO hypermesh_violation_operations(tenant_id,operation_id,lease_id,binding) VALUES(:id,:operation,:lease,\'retained\')'), {'id':identifier,'operation':uuid.uuid4(),'lease':uuid.uuid4()})
            migrations.upgrade(url)
            assert migrations.current_heads(url) == migrations.chain_heads()
            assert migrations.chain_heads()['hypermesh'] == 'hypermesh_0088_safe_tenant_guc'
            with engine.begin() as connection:
                assert connection.scalar(text("SELECT count(*) FROM tenants WHERE id=:id"), {'id':identifier}) == 1
                assert connection.scalar(text("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='hypermesh_jobs' AND column_name='lab_binding'")) == 1
                assert connection.scalar(text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='public.hypermesh_violation_operations'::regclass")) is True
                connection.execute(text('SELECT public.account_check_closure_worker_installation()'))
                if previous == 'hypermesh_0070_violation_ops':
                    assert connection.scalar(text('SELECT binding FROM hypermesh_violation_operations WHERE tenant_id=:id'), {'id':identifier}) == 'retained'
            migrations.upgrade(url)
            assert migrations.current_heads(url) == migrations.chain_heads()
        finally:
            engine.dispose()


@pytest.mark.parametrize('previous', ['payment_service_0081_test_gc', 'payment_service_0081_location'])
def test_test_guards_and_payout_location_histories_preserve_both_owners(previous):
    with disposable_database() as url:
        engine = create_engine(url)
        tenant, host, revision = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        legacy_role = 'legacy_test_' + uuid.uuid4().hex
        try:
            with engine.begin() as connection:
                # Build each actual former single-head image from its immutable
                # migrations, rather than downgrading a merge into two heads.
                for chain in migrations._ORDER:
                    target = previous if chain == 'payment_service' else 'head'
                    if chain == 'platform':
                        target = ('platform_0079_closure_merge' if previous == 'payment_service_0081_location'
                                  else 'platform_0080_test_retention')
                    command.upgrade(migrations._config(migrations._ROOT, chain, connection), target)
                if previous == 'payment_service_0081_test_gc':
                    assert connection.scalar(text("SELECT to_regprocedure('public.account_lock_test_financial_sources(text,timestamptz)')")) is None
                    assert connection.scalar(text("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='account_test_delete_capabilities'")) == 3
                    connection.execute(text(f'CREATE ROLE {legacy_role} NOLOGIN NOSUPERUSER BYPASSRLS'))
                    connection.execute(text(f'GRANT SELECT,INSERT,DELETE ON public.account_test_delete_capabilities TO {legacy_role}'))
                    connection.execute(text(f'GRANT INSERT(transaction_id,relation,row_digest) ON public.account_test_delete_capabilities TO {legacy_role}'))
                connection.execute(text("INSERT INTO tenants(id,name,is_active) VALUES(:t,'retained-payment-history',true)"), {'t': tenant})
                if previous == 'payment_service_0081_location':
                    connection.execute(text("INSERT INTO connect_payout_locations(tenant_id,host_org_id,revision,status) VALUES(:t,:h,:r,'pending')"), {'t': tenant, 'h': host, 'r': revision})
            migrations.upgrade(url)
            assert migrations.current_heads(url) == migrations.chain_heads()
            assert migrations.chain_heads()['payment_service'] == 'payment_service_0082_test_merge'
            with engine.begin() as connection:
                assert connection.scalar(text("SELECT count(*) FROM tenants WHERE id=:t"), {'t': tenant}) == 1
                assert connection.scalar(text("SELECT relrowsecurity AND relforcerowsecurity FROM pg_class WHERE oid='public.connect_payout_locations'::regclass")) is True
                if previous == 'payment_service_0081_location':
                    assert connection.scalar(text("SELECT revision FROM connect_payout_locations WHERE tenant_id=:t AND host_org_id=:h"), {'t': tenant, 'h': host}) == revision
                definition = connection.scalar(text("SELECT pg_get_functiondef('public.connect_recipient_immutable()'::regprocedure)"))
                assert definition.count('account_test_row_delete_allowed') == 1
                assert connection.scalar(text('SELECT public.account_test_data_enabled()')) is False
                assert connection.scalar(text("SELECT to_regprocedure('public.account_lock_test_financial_sources(text,timestamptz)') IS NOT NULL")) is True
                assert connection.scalar(text("SELECT count(*) FROM information_schema.columns WHERE table_schema='public' AND table_name='account_test_delete_capabilities'")) == 6
                if previous == 'payment_service_0081_test_gc':
                    assert connection.scalar(text("SELECT has_table_privilege(:role,'public.account_test_delete_capabilities','SELECT,INSERT,UPDATE,DELETE,TRUNCATE')"), {'role':legacy_role}) is False
                    assert connection.scalar(text("SELECT has_any_column_privilege(:role,'public.account_test_delete_capabilities','SELECT,INSERT,UPDATE,REFERENCES')"), {'role':legacy_role}) is False
                    assert connection.scalar(text("SELECT has_function_privilege(:role,'public.account_stage_test_delete(text,timestamptz,oid,text,oid,text)','EXECUTE')"), {'role':legacy_role}) is False
                connection.execute(text('SELECT public.account_check_closure_worker_installation()'))
            migrations.upgrade(url)
            assert migrations.current_heads(url) == migrations.chain_heads()
        finally:
            with engine.begin() as connection:
                if connection.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname=:role)'), {'role':legacy_role}):
                    connection.execute(text(f'DROP OWNED BY {legacy_role}'))
                    connection.execute(text(f'DROP ROLE {legacy_role}'))
            engine.dispose()


@pytest.mark.parametrize('previous',['platform_0084_stripe_clock','platform_0083_stripe_ancestry'])
def test_independent_stripe_guard_histories_preserve_data_and_downgrade(previous):
    with disposable_database() as url:
        engine=create_engine(url)
        tenant,payment=uuid.uuid4(),uuid.uuid4()
        try:
            with engine.begin() as c:
                for chain in migrations._ORDER:
                    command.upgrade(migrations._config(migrations._ROOT,chain,c),previous if chain=='platform' else 'head')
                c.execute(text("INSERT INTO tenants(id,name,is_active) VALUES(:t,'stripe-history',true)"),{'t':tenant})
                c.execute(text("INSERT INTO billing_records(id,tenant_id,scope,actor,payment_type,currency,amount,status,metadata) VALUES(:p,:t,'invoice','tenant','card','usd',100,'pending','{}'::jsonb)"),{'p':payment,'t':tenant})
                original=c.scalar(text('SELECT to_jsonb(b) FROM billing_records b WHERE id=:p'),{'p':payment})
            for attempt in range(2):
                migrations.upgrade(url)
                assert migrations.current_heads(url)==migrations.chain_heads()
                assert migrations.chain_heads()['platform']=='platform_0085_stripe_merge'
                with engine.begin() as c:
                    assert c.scalar(text('SELECT to_jsonb(b) FROM billing_records b WHERE id=:p'),{'p':payment})==original
                    assert c.scalar(text("SELECT to_regprocedure('public.account_test_stripe_metadata(jsonb)') IS NOT NULL")) is True
                    assert c.scalar(text("SELECT to_regprocedure('public.account_test_check_row_pre0083(text,jsonb)') IS NOT NULL")) is True
                    assert c.scalar(text('SELECT public.account_test_data_enabled()')) is False
                    assert c.scalar(text("SELECT count(*) FROM account_test_policy_originals WHERE signature LIKE 'platform_0084_stripe_clock:%'"))==1
                # A merge splits into both parents on one-step downgrade.
                # Roll back to their genuine common predecessor, then rebuild
                # the selected original single-head image without stamping.
                with engine.begin() as c:
                    command.downgrade(migrations._config(migrations._ROOT,'platform',c),'platform_0082_stripe_mode')
                assert migrations.current_heads(url)['platform']=='platform_0082_stripe_mode'
                with engine.begin() as c:
                    command.upgrade(migrations._config(migrations._ROOT,'platform',c),previous)
                assert migrations.current_heads(url)['platform']==previous
            migrations.upgrade(url)
        finally:
            engine.dispose()
