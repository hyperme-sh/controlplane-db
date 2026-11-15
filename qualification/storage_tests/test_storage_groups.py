"""CI-only storage retirement schema, tenant scope and serialization contracts."""
import importlib.util
import os
from sqlalchemy.engine import make_url
from pathlib import Path
import uuid
import psycopg
from psycopg import sql
import pytest
from test_storage_owner import database, migrate as baseline

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('storage_group_migrate',ROOT/'storage-schema/group_migrate.py')
group=importlib.util.module_from_spec(spec);spec.loader.exec_module(group)
pytestmark=pytest.mark.integration
OWNER='a'*43+'.'+'b'*43
OBJECT='set_p_'+'a'*128+'_'+'b'*32
SECOND='set_p_'+'a'*128+'_'+'c'*32
DIGEST='d'*64


def initialize(database):
    owner,app,schema,runtime=database
    assert baseline.apply(owner,schema,runtime)
    assert group.apply(owner,schema,runtime)
    assert not group.apply(owner,schema,runtime)
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
    app.execute("INSERT INTO storage_group_objects(tenant_id,set_id,predicate,owner_principal,source_id,allocation_id,issuer_id,policy_digest,creation_digest,issued_at,expires_at) VALUES (%s,%s,'same-group',%s,%s,%s,%s,%s,%s,1000,1300)",(tenant,object,OWNER,uuid.uuid4(),uuid.uuid4(),uuid.uuid4(),'a'*64,'b'*64))


def ref(app,tenant,object=OBJECT):
    app.execute("INSERT INTO storage_group_refs VALUES (%s,%s,%s,33)",(tenant,object,DIGEST))


def test_retirement_is_monotonic_and_shared_references_survive(database):
    _,app,_,_=database;tenant,_=initialize(database)
    insert(app,tenant);insert(app,tenant,SECOND);ref(app,tenant);ref(app,tenant,SECOND)
    with pytest.raises(psycopg.errors.RaiseException):
        app.execute('DELETE FROM storage_group_refs WHERE set_id=%s',(OBJECT,))
    app.execute('UPDATE storage_group_objects SET phase=1,deletion_command=%s WHERE set_id=%s',('e'*64,OBJECT))
    with pytest.raises(psycopg.errors.RaiseException):
        app.execute('UPDATE storage_group_objects SET phase=2 WHERE set_id=%s',(OBJECT,))
    with pytest.raises(psycopg.errors.RaiseException):ref(app,tenant)
    app.execute('DELETE FROM storage_group_refs WHERE set_id=%s',(OBJECT,))
    app.execute('UPDATE storage_group_objects SET phase=2 WHERE set_id=%s',(OBJECT,))
    app.execute('UPDATE storage_group_objects SET phase=2 WHERE set_id=%s',(OBJECT,))
    assert app.execute('SELECT set_id FROM storage_group_refs WHERE digest=%s',(DIGEST,)).fetchall()==[(SECOND,)]
    for query in ["UPDATE storage_group_objects SET phase=0,deletion_command=NULL WHERE set_id=%s",
                  "UPDATE storage_group_objects SET deletion_command='"+'f'*64+"' WHERE set_id=%s",
                  "UPDATE storage_group_objects SET owner_principal='"+('c'*43+'.'+'d'*43)+"' WHERE set_id=%s"]:
        with pytest.raises(psycopg.errors.RaiseException):app.execute(query,(OBJECT,))
    with pytest.raises(psycopg.errors.InsufficientPrivilege):app.execute('DELETE FROM storage_group_objects')
    with pytest.raises(psycopg.errors.UniqueViolation):insert(app,tenant)


def test_tenant_scope_and_runtime_ddl_refusal(database):
    _,app,schema,runtime=database;first,second=initialize(database)
    insert(app,first);ref(app,first)
    app.execute("SELECT set_config('app.current_tenant_id',%s,false)",(str(second),))
    assert app.execute('SELECT * FROM storage_group_objects').fetchall()==[]
    assert app.execute('SELECT * FROM storage_group_refs').fetchall()==[]
    with pytest.raises(psycopg.errors.InsufficientPrivilege):insert(app,first,SECOND)
    with pytest.raises(psycopg.errors.InsufficientPrivilege):app.execute('TRUNCATE storage_group_objects CASCADE')
    with pytest.raises(psycopg.errors.InsufficientPrivilege):app.execute('ALTER TABLE storage_group_objects DISABLE TRIGGER ALL')
    with pytest.raises(ValueError,match='roles must differ'):group.apply(app,schema,runtime)


def test_pending_reference_transaction_serializes_retirement(database):
    _,app,schema,runtime=database;tenant,_=initialize(database)
    insert(app,tenant)
    url=make_url(os.environ['TEST_DATABASE_URL']).set(drivername='postgresql').render_as_string(hide_password=False)
    with psycopg.connect(url,autocommit=True) as other:
        other.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(runtime)))
        other.execute(sql.SQL('SET search_path TO {},pg_catalog').format(sql.Identifier(schema)))
        other.execute("SELECT set_config('app.current_tenant_id',%s,false)",(str(tenant),))
        other.execute("SET lock_timeout='100ms'")
        with app.transaction():
            ref(app,tenant)
            with pytest.raises(psycopg.errors.LockNotAvailable):
                other.execute('UPDATE storage_group_objects SET phase=1,deletion_command=%s WHERE set_id=%s',('e'*64,OBJECT))
        other.execute('UPDATE storage_group_objects SET phase=1,deletion_command=%s WHERE set_id=%s',('e'*64,OBJECT))
        with pytest.raises(psycopg.errors.RaiseException):ref(app,tenant)


def test_changed_bundle_refuses_without_rewriting_metadata(database,tmp_path,monkeypatch):
    owner,app,schema,runtime=database;initialize(database)
    changed=tmp_path/'changed.sql';changed.write_bytes(group.DDL.read_bytes()+b'\n-- changed\n')
    monkeypatch.setattr(group,'DDL',changed)
    with pytest.raises(ValueError,match='version differs'):group.apply(owner,schema,runtime)


def test_temporary_relations_cannot_shadow_transition_guards(database):
    _,app,schema,_=database;tenant,_=initialize(database)
    insert(app,tenant);ref(app,tenant)
    objects=sql.Identifier(schema,'storage_group_objects')
    refs=sql.Identifier(schema,'storage_group_refs')
    app.execute('CREATE TEMP TABLE storage_group_refs (tenant_id uuid, set_id text)')
    app.execute(sql.SQL('UPDATE {} SET phase=1,deletion_command=%s WHERE set_id=%s').format(objects),('e'*64,OBJECT))
    with pytest.raises(psycopg.errors.RaiseException):
        app.execute(sql.SQL('UPDATE {} SET phase=2 WHERE set_id=%s').format(objects),(OBJECT,))
    app.execute('CREATE TEMP TABLE storage_group_objects (tenant_id uuid,set_id text,phase smallint)')
    app.execute('INSERT INTO pg_temp.storage_group_objects VALUES (%s,%s,0)',(tenant,OBJECT))
    with pytest.raises(psycopg.errors.RaiseException):
        app.execute(sql.SQL("INSERT INTO {} VALUES (%s,%s,%s,33)").format(refs),(tenant,OBJECT,'f'*64))
    assert app.execute(sql.SQL('SELECT count(*) FROM {}').format(refs)).fetchone()==(1,)


def test_allocation_identifier_cannot_move_to_another_source(database):
    _,app,_,_=database;tenant,_=initialize(database)
    insert(app,tenant)
    allocation=app.execute('SELECT allocation_id FROM storage_group_objects').fetchone()[0]
    with pytest.raises(psycopg.errors.UniqueViolation):
        app.execute("INSERT INTO storage_group_objects(tenant_id,set_id,predicate,owner_principal,source_id,allocation_id,issuer_id,policy_digest,creation_digest,issued_at,expires_at) VALUES (%s,%s,'same-group',%s,%s,%s,%s,%s,%s,1000,1300)",(tenant,SECOND,OWNER,uuid.uuid4(),allocation,uuid.uuid4(),'a'*64,'b'*64))


def test_group_and_wrap_capacity_are_reserved_before_provider_writes(database):
    _,app,_,_=database;tenant,_=initialize(database)
    for i in range(64):insert(app,tenant,'set_p_'+'a'*128+'_'+f'{i:032x}')
    with pytest.raises(psycopg.errors.RaiseException,match='capacity'):insert(app,tenant)
    set_id='set_p_'+'a'*128+'_'+'0'*32
    app.execute("INSERT INTO storage_group_refs SELECT %s,%s,lpad(to_hex(n),64,'0'),65536 FROM generate_series(1,4096) AS n",(tenant,set_id))
    with pytest.raises(psycopg.errors.RaiseException,match='capacity'):
        app.execute('INSERT INTO storage_group_refs VALUES (%s,%s,%s,1)',(tenant,set_id,'f'*64))
    assert app.execute('SELECT count(*),sum(byte_length) FROM storage_group_refs WHERE set_id=%s',(set_id,)).fetchone()==(4096,268435456)


def test_group_shape_and_immutable_predicate_refuse_media_reuse(database):
    _,app,_,_=database;tenant,_=initialize(database)
    with pytest.raises(psycopg.errors.CheckViolation):insert(app,tenant,OBJECT.replace('set_p_','media_p_'))
    insert(app,tenant)
    with pytest.raises(psycopg.errors.RaiseException):
        app.execute("UPDATE storage_group_objects SET predicate='named-circle'")
    for size in (0,65537):
        with pytest.raises(psycopg.errors.CheckViolation):
            app.execute('INSERT INTO storage_group_refs VALUES (%s,%s,%s,%s)',(tenant,OBJECT,DIGEST,size))
