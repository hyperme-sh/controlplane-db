"""Disposable owner database fixtures; no deployed endpoint is used by CI."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from controlplane_db import migrations


@pytest.fixture(scope="session")
def migration_templates():
    from migration_test_support import MigrationTemplates
    raw = os.environ.get('TEST_DATABASE_URL')
    if not raw:
        pytest.fail('TEST_DATABASE_URL must select a disposable administrative PostgreSQL server')
    templates = MigrationTemplates(raw, prefix='owner_' + uuid.uuid4().hex[:8])
    try:
        yield templates
    finally:
        # Close the admin pool; the disposable server owns session templates.
        templates.dispose()


@pytest.fixture
def migration_database(migration_templates):
    created = []
    def make(revision=None, *, template=None):
        if template is None:
            template = migration_templates.template_at(revision) if revision else 'template0'
        name, url = migration_templates.database(template)
        created.append(name)
        return url
    try:
        yield make
    finally:
        for name in created:
            migration_templates.drop(name)


@pytest.fixture
def migration_db(request, migration_database):
    marker = request.node.get_closest_marker('migration_start')
    return migration_database(marker.args[0] if marker else None)


@pytest.fixture(autouse=True)
def restore_migration_environment():
    old = os.environ.get('DATABASE_URL')
    try:
        yield
    finally:
        if old is None:
            os.environ.pop('DATABASE_URL', None)
        else:
            os.environ['DATABASE_URL'] = old


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


def pytest_configure(config):
    config.addinivalue_line('markers', 'integration: disposable PostgreSQL owner integration')
    config.addinivalue_line('markers', 'migration_start(revision): frozen historical starting revision')
