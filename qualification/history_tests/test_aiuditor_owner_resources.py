"""New product resources upgrade the independent owner lineage, not Panopticon."""
import os
import uuid

import pytest
from alembic import command
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from controlplane_db import migrations


def test_report_and_enforcement_upgrade_and_tenant_rls():
    raw = os.environ.get('TEST_DATABASE_URL')
    if not raw:
        pytest.skip('requires a disposable administrative PostgreSQL TEST_DATABASE_URL')
    name = 'owner_reports_' + uuid.uuid4().hex
    admin = create_engine(raw, isolation_level='AUTOCOMMIT')
    engine = None
    created = False
    try:
        with admin.connect() as cx:
            cx.exec_driver_sql(f'CREATE DATABASE "{name}"')
            created = True
        url = make_url(raw).set(database=name).render_as_string(hide_password=False)
        migrations.upgrade(url, baseline_only=True)
        migrations.prepare_event_source_index(url)
        migrations.upgrade(url, chains=('platform', 'events'))
        engine = create_engine(url)
        with engine.begin() as cx:
            for chain, revision in [('hypermesh', 'hypermesh_0068_environment_cert'),
                                    ('aiuditor', 'aiuditor_0056_crawl_state')]:
                command.upgrade(migrations._config(migrations._ROOT, chain, cx), revision)
        tenant, other, envelope = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        with engine.begin() as cx:
            for tid in (tenant, other):
                cx.execute(text('INSERT INTO tenants(id,name,is_active) VALUES(:id,:name,true)'),
                           {'id':tid, 'name':str(tid)})
            cx.execute(text('''INSERT INTO aiuditor_envelopes
                (id,tenant_id,class_id,catalog_id,file_hash,runtime,fit,created_at,updated_at)
                VALUES(:id,:tid,'test-class','test-model',:hash,'test-runtime',true,now(),now())'''),
                {'id':envelope,'tid':tenant,'hash':'sha256:'+'a'*64})
        migrations.upgrade(url, chains=('hypermesh', 'aiuditor'))
        migrations.upgrade(url, chains=('hypermesh', 'aiuditor'))
        heads = migrations.current_heads(url)
        assert heads['hypermesh'] == 'hypermesh_0088_safe_tenant_guc'
        assert heads['aiuditor'] == 'aiuditor_0058_enforcement'
        assert 'lab_binding' in {c['name'] for c in inspect(engine).get_columns('hypermesh_jobs')}
        assert {'enforcement_attempts','enforcement_completed_at'} <= {
            c['name'] for c in inspect(engine).get_columns('aiuditor_violations')}
        with engine.begin() as cx:
            assert cx.execute(text('SELECT lab_job_id,report_sha256,measured_at FROM aiuditor_envelopes WHERE id=:id'), {'id':envelope}).one() == (None,None,None)
            for table in ('aiuditor_envelope_reports','hypermesh_violation_operations'):
                assert cx.execute(text('SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE relname=:name'), {'name':table}).one() == (True,True)
            for tid in (tenant,other):
                cx.execute(text('''INSERT INTO aiuditor_envelope_reports
                    (tenant_id,origin,job_id,payload_sha256,accepted_envelope,received_at)
                    VALUES(:tid,'path_b',:job,:hash,'{}',now())'''),
                    {'tid':tid,'job':uuid.uuid4(),'hash':'b'*64})
                cx.execute(text('''INSERT INTO hypermesh_violation_operations
                    (tenant_id,operation_id,lease_id,binding) VALUES(:tid,:op,:lease,'test-binding')'''),
                    {'tid':tid,'op':uuid.uuid4(),'lease':uuid.uuid4()})
            # A transaction-local role cannot bypass RLS even if the connection is administrative.
            role = 'report_reader_' + uuid.uuid4().hex
            cx.exec_driver_sql(f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS')
            try:
                cx.exec_driver_sql(f'GRANT USAGE ON SCHEMA public TO "{role}"')
                cx.exec_driver_sql(f'GRANT SELECT ON aiuditor_envelope_reports,hypermesh_violation_operations TO "{role}"')
                cx.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
                for value, count in [('',0),(str(tenant),1),(str(other),1)]:
                    cx.execute(text("SELECT set_config('app.current_tenant_id',:tid,true)"), {'tid':value})
                    for table in ('aiuditor_envelope_reports','hypermesh_violation_operations'):
                        rows = cx.execute(text(f'SELECT tenant_id FROM {table}')).scalars().all()
                        assert len(rows) == count
                        assert all(str(tid) == value for tid in rows)
            finally:
                cx.exec_driver_sql('RESET ROLE')
                cx.exec_driver_sql(f'DROP OWNED BY "{role}"')
                cx.exec_driver_sql(f'DROP ROLE "{role}"')
    finally:
        if engine is not None:
            engine.dispose()
        if created:
            with admin.connect() as cx:
                cx.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
        admin.dispose()
