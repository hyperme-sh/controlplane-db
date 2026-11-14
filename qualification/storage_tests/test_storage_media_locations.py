"""CI provider binding permanence, legacy refusal and tenant isolation."""
import importlib.util
from pathlib import Path
import psycopg
from psycopg import sql
import pytest
from test_storage_owner import database
from test_storage_media import initialize,insert,ref,OBJECT,SECOND

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('storage_locations_migrate',ROOT/'storage-schema/media_location_migrate.py')
locations=importlib.util.module_from_spec(spec);spec.loader.exec_module(locations)
pytestmark=pytest.mark.integration


def test_permanent_binding_and_legacy_reference_refusal(database):
    owner,app,schema,runtime=database;tenant,other=initialize(database)
    insert(app,tenant);insert(app,tenant,SECOND);ref(app,tenant,SECOND)
    assert locations.apply(owner,schema,runtime)
    assert not locations.apply(owner,schema,runtime)
    app.execute('INSERT INTO storage_media_locations VALUES (%s,%s,%s)',(tenant,OBJECT,'a'*64))
    with pytest.raises(psycopg.errors.RaiseException):
        app.execute('INSERT INTO storage_media_locations VALUES (%s,%s,%s)',(tenant,SECOND,'b'*64))
    for query in ['UPDATE storage_media_locations SET provider_location=%s','DELETE FROM storage_media_locations WHERE provider_location=%s']:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):app.execute(query,('a'*64,))
    owner.execute("SELECT set_config('app.current_tenant_id',%s,false)",(str(tenant),))
    with pytest.raises(psycopg.errors.RaiseException):owner.execute('UPDATE storage_media_locations SET provider_location=%s',('b'*64,))
    app.execute("SELECT set_config('app.current_tenant_id',%s,false)",(str(other),))
    assert app.execute('SELECT * FROM storage_media_locations').fetchall()==[]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):app.execute('INSERT INTO storage_media_locations VALUES (%s,%s,%s)',(tenant,OBJECT,'a'*64))
    with pytest.raises(ValueError):locations.apply(app,schema,runtime)
