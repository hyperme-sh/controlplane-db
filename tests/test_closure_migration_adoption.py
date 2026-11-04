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
            assert migrations.chain_heads()['platform'] == 'platform_0079_closure_merge'
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
