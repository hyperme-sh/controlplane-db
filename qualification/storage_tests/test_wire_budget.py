"""CI-only PostgreSQL aggregate wire budget and restricted-role contracts."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
import threading
import os
from sqlalchemy.engine import make_url
import uuid
import psycopg
from psycopg import sql
import pytest
from test_storage_owner import database

spec=importlib.util.spec_from_file_location('wire_migrate',Path(__file__).resolve().parents[2]/'storage-schema/wire_migrate.py')
migrate=importlib.util.module_from_spec(spec);spec.loader.exec_module(migrate)
pytestmark=pytest.mark.integration


def setup(database, budget=1000):
    owner,app,schema,runtime=database
    assert migrate.apply(owner,schema,runtime)
    assert not migrate.apply(owner,schema,runtime)
    owner.execute(sql.SQL('SET search_path TO {},pg_catalog').format(sql.Identifier(schema)))
    tenant,generation=uuid.uuid4(),uuid.uuid4()
    for db in (owner,app):db.execute("SELECT set_config('app.current_tenant_id',%s,false)",(str(tenant),))
    owner.execute('INSERT INTO tenants VALUES (%s)',(tenant,))
    owner.execute('INSERT INTO wire_policies VALUES (%s,%s,%s,true)',(tenant,budget,generation))
    return tenant,generation


def reserve(app,tenant,generation,amount=500,purpose='turn',now=None,expires=None):
    now=now if now is not None else int(app.execute('SELECT floor(extract(epoch FROM clock_timestamp()))').fetchone()[0])
    expires=expires if expires is not None else min(now+30,(now//86400+1)*86400)
    rid=uuid.uuid4()
    app.execute('INSERT INTO wire_reservations(tenant_id,reservation_id,generation,consumer,purpose,issued_at,expires_at,reserved_bytes) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)',
                (tenant,rid,generation,uuid.uuid4(),purpose,now,expires,amount))
    return rid


def test_cross_purpose_budget_and_single_use_claim(database):
    owner,app,_,_=database;tenant,generation=setup(database)
    rid=reserve(app,tenant,generation)
    reserve(app,tenant,generation,purpose='mediamtx')
    app.execute('UPDATE wire_reservations SET claimed=true WHERE reservation_id=%s',(rid,))
    for query in ['UPDATE wire_reservations SET claimed=true','DELETE FROM wire_reservations',
                  'UPDATE wire_reservations SET reserved_bytes=1','UPDATE wire_policies SET enabled=true']:
        with pytest.raises(psycopg.Error):app.execute(query)
    with pytest.raises(psycopg.errors.RaiseException,match='budget exhausted'):reserve(app,tenant,generation,1)
    # Generation rotation and process restart cannot create a second daily pool.
    generation=uuid.uuid4();owner.execute('UPDATE wire_policies SET generation=%s',(generation,))
    with pytest.raises(psycopg.errors.RaiseException,match='budget exhausted'):reserve(app,tenant,generation,1)


def test_disabled_scope_and_utc_bounds(database):
    owner,app,_,_=database;tenant,generation=setup(database)
    owner.execute('UPDATE wire_policies SET enabled=false')
    with pytest.raises(psycopg.errors.RaiseException):reserve(app,tenant,generation)
    owner.execute('UPDATE wire_policies SET enabled=true')
    now=int(app.execute('SELECT floor(extract(epoch FROM clock_timestamp()))').fetchone()[0])
    with pytest.raises(psycopg.Error):reserve(app,tenant,generation,now=now,expires=(now//86400+1)*86400+1)
    with pytest.raises(psycopg.Error):reserve(app,tenant,generation,purpose='seed')
    with pytest.raises(psycopg.Error):owner.execute('UPDATE wire_policies SET daily_bytes=32000000001')
    reserve(app,tenant,generation)
    app.execute("SELECT set_config('app.current_tenant_id',%s,false)",(str(uuid.uuid4()),))
    assert app.execute('SELECT * FROM wire_reservations').fetchall()==[]
    with pytest.raises(psycopg.Error):reserve(app,tenant,generation)


def test_concurrent_consumers_share_one_pool(database):
    owner,app,schema,runtime=database;tenant,generation=setup(database)
    barrier=threading.Barrier(2)
    def contender(purpose):
        with psycopg.connect(make_url(os.environ["TEST_DATABASE_URL"]).set(drivername="postgresql").render_as_string(hide_password=False),autocommit=True) as db:
            db.execute(sql.SQL('SET ROLE {}').format(sql.Identifier(runtime)))
            db.execute(sql.SQL('SET search_path TO {},pg_catalog').format(sql.Identifier(schema)))
            db.execute("SELECT set_config('app.current_tenant_id',%s,false)",(str(tenant),))
            barrier.wait(timeout=10)
            try:reserve(db,tenant,generation,750,purpose);return True
            except psycopg.errors.RaiseException:return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(contender,['turn','mediamtx']))==[False,True]
    assert app.execute('SELECT sum(reserved_bytes) FROM wire_reservations').fetchone()==(750,)


def test_future_allowance_cannot_become_usable_early(database):
    owner,app,_,_=database;tenant,generation=setup(database)
    # A future issuance within the old two-second tolerance must be refused,
    # including the upcoming UTC day. No wall-clock midnight wait is needed.
    now=int(app.execute('SELECT floor(extract(epoch FROM clock_timestamp()))').fetchone()[0])+2
    with pytest.raises(psycopg.errors.RaiseException,match='policy unavailable'):
        reserve(app,tenant,generation,now=now)
    assert app.execute('SELECT count(*) FROM wire_reservations').fetchone()==(0,)
