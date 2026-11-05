"""Disposable owner database fixtures; no deployed endpoint is used by CI."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from controlplane_db import migrations


@pytest.fixture
def migration_database():
    raw = os.environ.get('TEST_DATABASE_URL')
    if not raw:
        pytest.fail('TEST_DATABASE_URL must select a disposable administrative PostgreSQL server')
    admin = create_engine(raw, isolation_level='AUTOCOMMIT')
    created = []

    def make():
        name = 'owner_test_' + uuid.uuid4().hex
        with admin.connect() as cx:
            cx.exec_driver_sql(f'CREATE DATABASE "{name}" TEMPLATE template0')
        created.append(name)
        return make_url(raw).set(database=name).render_as_string(hide_password=False)

    try:
        yield make
    finally:
        with admin.connect() as cx:
            for name in created:
                cx.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
        admin.dispose()


@pytest.fixture
def migrated_postgres(migration_database):
    url = migration_database()
    migrations.upgrade(url)
    return url


@pytest.fixture
def rls_isolation_role_ready(migrated_postgres):
    engine = create_engine(migrated_postgres)
    role = 'spanopticon_rls_tester'
    with engine.begin() as cx:
        cx.execute(text(f'CREATE ROLE {role} NOINHERIT NOBYPASSRLS'))
        cx.execute(text(f'GRANT SELECT ON billing_records TO {role}'))
        cx.execute(text(f'GRANT {role} TO CURRENT_USER'))
    try:
        yield
    finally:
        with engine.begin() as cx:
            cx.execute(text(f'DROP OWNED BY {role}'))
            cx.execute(text(f'DROP ROLE {role}'))
        engine.dispose()
