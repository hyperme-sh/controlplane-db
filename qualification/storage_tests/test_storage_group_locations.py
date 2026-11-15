"""CI provider binding permanence, legacy refusal and tenant isolation."""
import importlib.util
from pathlib import Path
import psycopg
from psycopg import sql
import pytest
from test_storage_owner import database
from test_storage_groups import initialize,insert,ref,OBJECT,SECOND

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('storage_locations_migrate',ROOT/'storage-schema/group_location_migrate.py')
locations=importlib.util.module_from_spec(spec);spec.loader.exec_module(locations)
pytestmark=pytest.mark.integration


def test_permanent_binding_and_legacy_reference_refusal(database):
    owner,app,schema,runtime=database;tenant,other=initialize(database)
    insert(app,tenant);insert(app,tenant,SECOND);ref(app,tenant,SECOND)
    assert locations.apply(owner,schema,runtime)
    assert not locations.apply(owner,schema,runtime)
    app.execute('INSERT INTO storage_group_locations VALUES (%s,%s,%s)',(tenant,OBJECT,'a'*64))
    with pytest.raises(psycopg.errors.RaiseException):
        app.execute('INSERT INTO storage_group_locations VALUES (%s,%s,%s)',(tenant,SECOND,'b'*64))
    for query in ['UPDATE storage_group_locations SET provider_location=%s','DELETE FROM storage_group_locations WHERE provider_location=%s']:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):app.execute(query,('a'*64,))
    owner.execute("SELECT set_config('app.current_tenant_id',%s,false)",(str(tenant),))
    with pytest.raises(psycopg.errors.RaiseException):owner.execute('UPDATE storage_group_locations SET provider_location=%s',('b'*64,))
    app.execute("SELECT set_config('app.current_tenant_id',%s,false)",(str(other),))
    assert app.execute('SELECT * FROM storage_group_locations').fetchall()==[]
    with pytest.raises((psycopg.errors.InsufficientPrivilege,psycopg.errors.RaiseException)):app.execute('INSERT INTO storage_group_locations VALUES (%s,%s,%s)',(tenant,OBJECT,'a'*64))
    with pytest.raises(ValueError):locations.apply(app,schema,runtime)


@pytest.mark.parametrize('isolation', ['REPEATABLE READ', 'SERIALIZABLE'])
def test_provider_binding_rejects_stale_snapshot(database,isolation):
    owner,app,schema,runtime=database;tenant,_=initialize(database)
    insert(app,tenant)
    locations.apply(owner,schema,runtime)
    with pytest.raises(psycopg.errors.RaiseException,match='read committed'):
        with app.transaction():
            app.execute('SET TRANSACTION ISOLATION LEVEL '+isolation)
            app.execute('INSERT INTO storage_group_locations VALUES (%s,%s,%s)',(tenant,OBJECT,'a'*64))
    assert app.execute('SELECT count(*) FROM storage_group_locations').fetchone()==(0,)


def test_changed_location_bundle_refuses_rewrite(database,tmp_path,monkeypatch):
    owner,app,schema,runtime=database;initialize(database)
    locations.apply(owner,schema,runtime)
    changed=tmp_path/'locations.sql'
    changed.write_bytes(locations.DDL.read_bytes()+b'\n-- changed\n')
    monkeypatch.setattr(locations,'DDL',changed)
    with pytest.raises(ValueError,match='differs'):locations.apply(owner,schema,runtime)
