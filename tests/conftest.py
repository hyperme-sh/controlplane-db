"""Fresh generic-model fixtures.

Frozen owner histories stay in the checkout and are qualified by
qualification/history_tests, not by this installed-package suite.
"""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from controlplane_db.base import Base
import controlplane_db.models


@pytest.fixture
def migrated_postgres():
    raw = os.environ.get('TEST_DATABASE_URL')
    if not raw:
        pytest.fail('TEST_DATABASE_URL must select disposable administrative PostgreSQL')
    url = make_url(raw).set(drivername='postgresql+psycopg')
    name = 'generic_db_' + uuid.uuid4().hex
    admin = create_engine(url, isolation_level='AUTOCOMMIT')
    engine = None
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
        target = url.set(database=name)
        engine = create_engine(target)
        Base.metadata.create_all(engine)
        with engine.begin() as connection:
            connection.exec_driver_sql('''
                ALTER TABLE crypto_agent_budgets ENABLE ROW LEVEL SECURITY;
                ALTER TABLE crypto_agent_budgets FORCE ROW LEVEL SECURITY;
                CREATE POLICY budget_tenant ON crypto_agent_budgets
                USING (tenant_id = nullif(current_setting('app.current_tenant_id', true),'')::uuid)
                WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant_id', true),'')::uuid);
            ''')
        yield target.render_as_string(hide_password=False)
    finally:
        if engine is not None:
            engine.dispose()
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()
