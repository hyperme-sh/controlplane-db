"""Scoped PostgreSQL migration checks; CI supplies the Infra-owned database.

Parent tables are minimal schema fixtures, not the full platform history.
"""
import importlib.util
import os
from pathlib import Path
from uuid import uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

PATH = Path(__file__).parents[2]/'src/controlplane_db/migration_chains/platform/versions/0088_org_user_memberships.py'
spec = importlib.util.spec_from_file_location('org_membership_revision', PATH)
revision = importlib.util.module_from_spec(spec)
spec.loader.exec_module(revision)


@pytest.fixture
def schema():
    engine = create_engine(os.environ['TEST_DATABASE_URL'])
    name = 'org_membership_' + uuid4().hex
    tenant, other, org, foreign_org, user, foreign_user = [uuid4() for _ in range(6)]
    with engine.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{name}"')
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{name}", public')
        connection.exec_driver_sql('CREATE TABLE users (id uuid PRIMARY KEY, tenant_id uuid)')
        connection.exec_driver_sql('CREATE TABLE organizations (id uuid PRIMARY KEY, tenant_id uuid NOT NULL, UNIQUE(id, tenant_id))')
        for table, values in [('users', [(user, tenant), (foreign_user, other)]), ('organizations', [(org, tenant), (foreign_org, other)])]:
            connection.execute(text(f'INSERT INTO {table} (id, tenant_id) VALUES (:id, :tenant)'), [dict(id=i, tenant=t) for i,t in values])
        with Operations.context(MigrationContext.configure(connection)):
            revision.upgrade()
    try:
        yield engine, name, dict(tenant=tenant, other=other, org=org, foreign_org=foreign_org, user=user, foreign_user=foreign_user)
    finally:
        with engine.begin() as connection: connection.exec_driver_sql(f'DROP SCHEMA "{name}" CASCADE')
        engine.dispose()


def add(connection, ids, role='member', **changes):
    values = dict(id=uuid4(), tenant=ids['tenant'], org=ids['org'], user=ids['user'], role=role)
    values.update(changes)
    connection.execute(text('INSERT INTO organization_user_memberships (id, tenant_id, organization_id, user_id, role) VALUES (:id, :tenant, :org, :user, :role)'), values)


def test_separate_roles_retry_uniqueness_and_foreign_tenant_refusal(schema):
    engine, name, ids = schema
    with engine.begin() as connection:
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{name}", public')
        for role in ('member', 'owner', 'admin'): add(connection, ids, role)
        assert connection.scalar(text('SELECT count(*) FROM organization_user_memberships')) == 3
        for changes, code in [({}, '23505'), ({'org':ids['foreign_org']}, '23503'), ({'user':ids['foreign_user']}, '23503'), ({'role':'platform_admin'}, '23514')]:
            with pytest.raises(DBAPIError) as error, connection.begin_nested(): add(connection, ids, **changes)
            assert error.value.orig.sqlstate == code
        assert connection.scalar(text('SELECT count(*) FROM organization_user_memberships')) == 3


def test_rls_refuses_missing_wrong_and_malformed_tenant_and_cross_tenant_updates(schema):
    engine, name, ids = schema
    role = 'org_reader_' + uuid4().hex
    with engine.begin() as connection:
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{name}", public')
        add(connection, ids)
        connection.exec_driver_sql(f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS')
        connection.exec_driver_sql(f'GRANT USAGE ON SCHEMA "{name}" TO "{role}"')
        connection.exec_driver_sql(f'GRANT SELECT, INSERT, UPDATE ON organization_user_memberships TO "{role}"')
        connection.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
        for tenant in ('', str(ids['other']), 'malformed'):
            connection.execute(text("SELECT set_config('app.current_tenant_id', :tenant, true)"), {'tenant':tenant})
            assert connection.scalar(text('SELECT count(*) FROM organization_user_memberships')) == 0
            with pytest.raises(DBAPIError), connection.begin_nested(): add(connection, ids, 'admin')
        connection.execute(text("SELECT set_config('app.current_tenant_id', :tenant, true)"), {'tenant':str(ids['tenant'])})
        assert connection.scalar(text('SELECT count(*) FROM organization_user_memberships')) == 1
        with pytest.raises(DBAPIError), connection.begin_nested():
            connection.execute(text('UPDATE organization_user_memberships SET tenant_id=:tenant, organization_id=:org, user_id=:user'),
                               dict(tenant=ids['other'], org=ids['foreign_org'], user=ids['foreign_user']))
        connection.exec_driver_sql('RESET ROLE')
        connection.exec_driver_sql(f'DROP OWNED BY "{role}"')
        connection.exec_driver_sql(f'DROP ROLE "{role}"')


def test_downgrade_preserves_nonempty_memberships_and_removes_only_empty_schema(schema):
    engine, name, ids = schema
    with engine.begin() as connection:
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{name}", public')
        add(connection, ids)
        with pytest.raises(DBAPIError), connection.begin_nested():
            with Operations.context(MigrationContext.configure(connection)): revision.downgrade()
        assert connection.scalar(text('SELECT count(*) FROM organization_user_memberships')) == 1
        connection.exec_driver_sql('DELETE FROM organization_user_memberships')
        with Operations.context(MigrationContext.configure(connection)): revision.downgrade()
        assert connection.scalar(text('SELECT count(*) FROM users')) == 2


def test_concurrent_identical_grants_create_one_row(schema):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    engine, name, ids = schema
    barrier = Barrier(2)
    def insert():
        try:
            with engine.begin() as connection:
                connection.exec_driver_sql(f'SET LOCAL search_path TO "{name}", public')
                barrier.wait(timeout=10)
                add(connection, ids, 'owner')
            return 'created'
        except DBAPIError as error:
            return error.orig.sqlstate
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: insert(), range(2)))
    assert sorted(results) == ['23505', 'created']
    with engine.begin() as connection:
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{name}", public')
        assert connection.scalar(text('SELECT count(*) FROM organization_user_memberships')) == 1
