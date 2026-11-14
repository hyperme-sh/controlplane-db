"""CI-only storage retirement schema, tenant scope and serialization contracts."""
import importlib.util
from pathlib import Path
import uuid
import psycopg
from psycopg import sql
import pytest
from test_storage_owner import database, migrate as baseline

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('storage_media_migrate',ROOT/'storage-schema/media_migrate.py')
media=importlib.util.module_from_spec(spec);spec.loader.exec_module(media)
pytestmark=pytest.mark.integration
OWNER='a'*43+'.'+'b'*43
OBJECT='media_p_'+'a'*128+'_'+'b'*32
SECOND='media_p_'+'a'*128+'_'+'c'*32
DIGEST='d'*64


def initialize(database):
    owner,app,schema,runtime=database
    assert baseline.apply(owner,schema,runtime)
    assert media.apply(owner,schema,runtime)
    assert not media.apply(owner,schema,runtime)
    # The frozen baseline runner remains compatible with the additive schema.
    assert not baseline.apply(owner,schema,runtime)
    owner.execute(sql.SQL('SET search_path TO {},pg_catalog').format(sql.Identifier(schema)))
    first,second=uuid.uuid4(),uuid.uuid4()
    for tenant in (first,second):
        owner.execute("SELECT set_config('app.current_tenant_id',%s,false)",(str(tenant),))
        owner.execute('INSERT INTO tenants(id) VALUES (%s)',(tenant,))
    app.execute("SELECT set_config('app.current_tenant_id',%s,false)",(str(first),))
    return first,second


def insert(app,tenant,object=OBJECT):
    app.execute('INSERT INTO storage_media_objects(tenant_id,object_id,owner_principal,source_id,allocation_id,issuer_id,policy_digest,ownership_digest,issued_at,expires_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,1000,1300)',(tenant,object,OWNER,uuid.uuid4(),uuid.uuid4(),uuid.uuid4(),'a'*64,'b'*64))


def ref(app,tenant,object=OBJECT):
    app.execute("INSERT INTO storage_media_refs VALUES (%s,%s,'ciphertext',%s,33)",(tenant,object,DIGEST))


def test_retirement_is_monotonic_and_shared_references_survive(database):
    _,app,_,_=database;tenant,_=initialize(database)
    insert(app,tenant);insert(app,tenant,SECOND);ref(app,tenant);ref(app,tenant,SECOND)
    with pytest.raises(psycopg.errors.RaiseException):
        app.execute('DELETE FROM storage_media_refs WHERE object_id=%s',(OBJECT,))
    app.execute('UPDATE storage_media_objects SET phase=1,deletion_command=%s WHERE object_id=%s',('e'*64,OBJECT))
    with pytest.raises(psycopg.errors.RaiseException):
        app.execute('UPDATE storage_media_objects SET phase=2 WHERE object_id=%s',(OBJECT,))
    with pytest.raises(psycopg.errors.RaiseException):ref(app,tenant)
    app.execute('DELETE FROM storage_media_refs WHERE object_id=%s',(OBJECT,))
    app.execute('UPDATE storage_media_objects SET phase=2 WHERE object_id=%s',(OBJECT,))
    app.execute('UPDATE storage_media_objects SET phase=2 WHERE object_id=%s',(OBJECT,))
    assert app.execute('SELECT object_id FROM storage_media_refs WHERE digest=%s',(DIGEST,)).fetchall()==[(SECOND,)]
    for query in ["UPDATE storage_media_objects SET phase=0,deletion_command=NULL WHERE object_id=%s",
                  "UPDATE storage_media_objects SET deletion_command='"+'f'*64+"' WHERE object_id=%s",
                  "UPDATE storage_media_objects SET owner_principal='"+('c'*43+'.'+'d'*43)+"' WHERE object_id=%s"]:
        with pytest.raises(psycopg.errors.RaiseException):app.execute(query,(OBJECT,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):app.execute('DELETE FROM storage_media_objects')
    with pytest.raises(psycopg.errors.UniqueViolation):insert(app,tenant)


def test_tenant_scope_and_runtime_ddl_refusal(database):
    _,app,schema,runtime=database;first,second=initialize(database)
    insert(app,first);ref(app,first)
    app.execute("SELECT set_config('app.current_tenant_id',%s,false)",(str(second),))
    assert app.execute('SELECT * FROM storage_media_objects').fetchall()==[]
    assert app.execute('SELECT * FROM storage_media_refs').fetchall()==[]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):insert(app,first,SECOND)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):app.execute('TRUNCATE storage_media_objects CASCADE')
    with pytest.raises(psycopg.errors.InsufficientPrivilege):app.execute('ALTER TABLE storage_media_objects DISABLE TRIGGER ALL')
    with pytest.raises(ValueError,match='roles must differ'):media.apply(app,schema,runtime)


def test_pending_reference_transaction_serializes_retirement(database):
    _,app,schema,runtime=database;tenant,_=initialize(database)
    insert(app,tenant)
    with psycopg.connect(app.info.dsn,autocommit=True) as other:
        other.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(runtime)))
        other.execute(sql.SQL('SET search_path TO {},pg_catalog').format(sql.Identifier(schema)))
        other.execute("SELECT set_config('app.current_tenant_id',%s,false)",(str(tenant),))
        other.execute("SET lock_timeout='100ms'")
        with app.transaction():
            ref(app,tenant)
            with pytest.raises(psycopg.errors.LockNotAvailable):
                other.execute('UPDATE storage_media_objects SET phase=1,deletion_command=%s WHERE object_id=%s',('e'*64,OBJECT))
        other.execute('UPDATE storage_media_objects SET phase=1,deletion_command=%s WHERE object_id=%s',('e'*64,OBJECT))
        with pytest.raises(psycopg.errors.RaiseException):ref(app,tenant)


def test_changed_bundle_refuses_without_rewriting_metadata(database,tmp_path,monkeypatch):
    owner,app,schema,runtime=database;initialize(database)
    changed=tmp_path/'changed.sql';changed.write_bytes(media.DDL.read_bytes()+b'\n-- changed\n')
    monkeypatch.setattr(media,'DDL',changed)
    with pytest.raises(ValueError,match='version differs'):media.apply(owner,schema,runtime)
