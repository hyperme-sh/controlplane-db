"""Disposable PostgreSQL stream capacity and isolation contracts, CI only."""
import importlib.util
from pathlib import Path
import uuid
import pytest
import psycopg
from psycopg import sql
from test_storage_owner import database

spec=importlib.util.spec_from_file_location('stream_migrate',Path(__file__).resolve().parents[2]/'storage-schema/stream_migrate.py')
migrate=importlib.util.module_from_spec(spec);spec.loader.exec_module(migrate)
pytestmark=pytest.mark.integration


def setup(database, budget=32*1024**3):
    owner,app,schema,runtime=database
    assert migrate.apply(owner,schema,runtime)
    assert not migrate.apply(owner,schema,runtime)
    owner.execute(sql.SQL('SET search_path TO {},pg_catalog').format(sql.Identifier(schema)))
    tenant,generation=uuid.uuid4(),uuid.uuid4()
    for db in (owner,app):db.execute("SELECT set_config('app.current_tenant_id',%s,false)",(str(tenant),))
    owner.execute('INSERT INTO tenants VALUES (%s)',(tenant,))
    owner.execute('INSERT INTO stream_policies VALUES (%s,%s,%s,true)',(tenant,budget,generation))
    return tenant,generation


def insert(app,tenant,generation,room='room',action='publish',path=None,ip='192.0.2.1'):
    rid=uuid.uuid4();now=int(app.execute('SELECT extract(epoch FROM clock_timestamp())').fetchone()[0])
    end=min(now+60,(now//86400+1)*86400)
    if action=='read':
        found=app.execute("SELECT expires_at FROM stream_sessions WHERE tenant_id=%s AND path=%s AND action='publish' AND phase=1",(tenant,path)).fetchone()
        if found:end=min(end,found[0])
    path=path or 'stream/'+tenant.hex+'/'+uuid.uuid4().hex
    app.execute('INSERT INTO stream_sessions(tenant_id,reservation_id,generation,room,principal,action,source_ip,token_hash,path,issued_at,expires_at,reserved_bytes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
        (tenant,rid,generation,room,'protected-principal',action,ip,rid.hex*2,path,now,end,(end-now)*391000))
    return rid,path


def test_publisher_reader_capacity_and_permanent_spend(database):
    owner,app,schema,runtime=database;tenant,generation=setup(database)
    rid,path=insert(app,tenant,generation)
    with pytest.raises(psycopg.errors.RaiseException):insert(app,tenant,generation)
    with pytest.raises(psycopg.errors.RaiseException):insert(app,tenant,generation,action='read',path=path)
    app.execute('UPDATE stream_sessions SET phase=1,media_session=%s WHERE reservation_id=%s',(uuid.uuid4(),rid))
    for _ in range(10):insert(app,tenant,generation,action='read',path=path)
    with pytest.raises(psycopg.errors.RaiseException):insert(app,tenant,generation,action='read',path=path)
    insert(app,tenant,generation,room='second',ip='192.0.2.2')
    with pytest.raises(psycopg.errors.RaiseException):insert(app,tenant,generation,room='third',ip='192.0.2.3')
    before=app.execute('SELECT sum(reserved_bytes) FROM stream_sessions').fetchone()[0]
    app.execute('UPDATE stream_sessions SET phase=2')
    app.execute('UPDATE stream_sessions SET phase=2')
    assert app.execute('SELECT sum(reserved_bytes) FROM stream_sessions').fetchone()[0]==before
    for query in ['DELETE FROM stream_sessions','UPDATE stream_policies SET enabled=true',"UPDATE stream_sessions SET phase=0", "UPDATE stream_sessions SET room='other'"]:
        with pytest.raises(psycopg.Error):app.execute(query)


def test_policy_scope_and_single_use_session(database):
    owner,app,_,_=database;tenant,generation=setup(database)
    rid,path=insert(app,tenant,generation)
    session=uuid.uuid4()
    app.execute('UPDATE stream_sessions SET phase=1,media_session=%s WHERE reservation_id=%s',(session,rid))
    with pytest.raises(psycopg.errors.RaiseException):
        app.execute('UPDATE stream_sessions SET media_session=%s WHERE reservation_id=%s',(uuid.uuid4(),rid))
    with pytest.raises(psycopg.errors.RaiseException):insert(app,tenant,uuid.uuid4(),room='other')
    owner.execute('UPDATE stream_policies SET enabled=false')
    with pytest.raises(psycopg.errors.RaiseException):insert(app,tenant,generation,room='other')
    # Closing remains possible even when authority is disabled.
    app.execute('UPDATE stream_sessions SET phase=2')
    app.execute("SELECT set_config('app.current_tenant_id',%s,false)",(str(uuid.uuid4()),))
    assert app.execute('SELECT * FROM stream_sessions').fetchall()==[]
    assert app.execute('SELECT * FROM stream_policies').fetchall()==[]


def test_closed_sessions_do_not_refund_daily_budget(database):
    owner,app,_,_=database;tenant,generation=setup(database,1407600000)
    # Charge a full hour, then close it. Neither close nor a new process refunds it.
    rid,path=insert(app,tenant,generation)
    owner.execute('UPDATE stream_policies SET daily_bytes=1407600000')
    app.execute('UPDATE stream_sessions SET phase=2')
    # Repeated short admissions must eventually hit the finite cap.
    refused=False
    for _ in range(100):
        try:insert(app,tenant,generation)
        except psycopg.errors.RaiseException:
            refused=True;break
        app.execute('UPDATE stream_sessions SET phase=2 WHERE phase<>2')
    assert refused
    assert app.execute('SELECT sum(reserved_bytes) FROM stream_sessions').fetchone()[0]<=1407600000
