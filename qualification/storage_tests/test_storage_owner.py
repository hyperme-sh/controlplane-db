"""CI-only disposable storage schema and restricted role contract."""
import importlib.util
import os
from pathlib import Path
import uuid

import psycopg
from psycopg import sql
import pytest
from sqlalchemy.engine import make_url

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('storage_migrate',ROOT/'storage-schema/migrate.py')
migrate=importlib.util.module_from_spec(spec);spec.loader.exec_module(migrate)
pytestmark=pytest.mark.integration


@pytest.fixture
def database():
    raw=os.environ.get('TEST_DATABASE_URL')
    if not raw: pytest.fail('CI disposable PostgreSQL is required')
    url=make_url(raw).set(drivername='postgresql').render_as_string(hide_password=False)
    suffix=uuid.uuid4().hex[:12]
    owner,schema,runtime='storage_m_'+suffix,'storage_s_'+suffix,'storage_r_'+suffix
    with psycopg.connect(url,autocommit=True) as admin:
        try:
            for role in (owner,runtime):
                admin.execute(sql.SQL('CREATE ROLE {} NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE').format(sql.Identifier(role)))
            admin.execute(sql.SQL('CREATE SCHEMA {} AUTHORIZATION {}').format(sql.Identifier(schema),sql.Identifier(owner)))
            with psycopg.connect(url,autocommit=True) as migrator, psycopg.connect(url,autocommit=True) as app:
                migrator.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(owner)))
                app.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(runtime)))
                app.execute(sql.SQL('SET search_path TO {},pg_catalog').format(sql.Identifier(schema)))
                yield migrator,app,schema,runtime
        finally:
            admin.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(schema)))
            for role in (runtime,owner): admin.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(role)))


def test_storage_owner_isolation_scope_and_idempotency(database):
    owner,app,schema,runtime=database
    assert migrate.apply(owner,schema,runtime)
    assert not migrate.apply(owner,schema,runtime)
    owner.execute(sql.SQL('SET search_path TO {},pg_catalog').format(sql.Identifier(schema)))
    first,second=uuid.uuid4(),uuid.uuid4()
    for tenant in (first,second):
        owner.execute("SELECT set_config('app.current_tenant_id',%s,false)",(str(tenant),))
        owner.execute('INSERT INTO tenants(id) VALUES (%s)',(tenant,))
    # Even the table owner is subject to FORCE RLS.
    assert owner.execute('SELECT id FROM tenants').fetchall()==[(second,)]
    assert app.execute('SELECT id FROM tenants').fetchall()==[]
    app.execute("SELECT set_config('app.current_tenant_id',%s,false)",(str(first),))
    assert app.execute('SELECT id FROM tenants FOR UPDATE').fetchall()==[(first,)]
    app.execute("INSERT INTO storage_settings(id,tenant_id,provider,is_enabled,region) VALUES (%s,%s,'s3',true,'us-east-1')",(uuid.uuid4(),first))
    with pytest.raises(psycopg.errors.UniqueViolation):
        app.execute("INSERT INTO storage_settings(id,tenant_id,provider,is_enabled,region) VALUES (%s,%s,'azure_blob',true,'global')",(uuid.uuid4(),first))
    app.execute("SELECT set_config('app.current_tenant_id',%s,false)",(str(second),))
    assert app.execute('SELECT id FROM storage_settings').fetchall()==[]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        app.execute("INSERT INTO storage_settings(id,tenant_id,provider,is_enabled,region) VALUES (%s,%s,'s3',false,'us-east-1')",(uuid.uuid4(),first))
    for statement in ['DELETE FROM storage_settings','CREATE TABLE forbidden(id integer)','INSERT INTO tenants(id) VALUES (gen_random_uuid())']:
        with pytest.raises(psycopg.errors.InsufficientPrivilege): app.execute(statement)
    with pytest.raises(ValueError,match='roles must differ'): migrate.apply(app,schema,runtime)


def test_changed_schema_bundle_is_not_silently_applied(database,tmp_path,monkeypatch):
    owner,app,schema,runtime=database
    assert migrate.apply(owner,schema,runtime)
    changed=tmp_path/'changed.sql';changed.write_bytes(migrate.DDL.read_bytes()+b'\n-- changed bundle\n')
    monkeypatch.setattr(migrate,'DDL',changed)
    with pytest.raises(ValueError,match='version differs'): migrate.apply(owner,schema,runtime)
