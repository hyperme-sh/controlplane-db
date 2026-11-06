"""Restricted roles must hydrate global rows without bypassing tenant isolation."""
import uuid
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from controlplane_db import migrations


def test_empty_scope_is_safe_for_every_hypermesh_policy(migration_db):
    migrations.upgrade(migration_db, ['platform', 'events', 'hypermesh'])
    engine = create_engine(migration_db)
    role = 'selfhost_rls_' + uuid.uuid4().hex[:12]
    try:
        with engine.begin() as cx:
            cx.execute(text(f'CREATE ROLE {role} NOSUPERUSER NOBYPASSRLS'))
            cx.execute(text(f'GRANT USAGE ON SCHEMA public TO {role}'))
            cx.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}'))
            policies = cx.execute(text("SELECT qual, with_check FROM pg_policies WHERE schemaname='public' AND tablename LIKE 'hypermesh\\_%' ESCAPE '\\'" )).all()
            assert policies
            unsafe = "(current_setting('app.current_tenant_id'::text, true))::uuid"
            assert all(unsafe not in (expression or '') for row in policies for expression in row)
            tables = cx.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'hypermesh\\_%' ESCAPE '\\'" )).scalars().all()
            tenants = [uuid.uuid4(), uuid.uuid4()]
            for tenant in tenants:
                cx.execute(text("INSERT INTO tenants(id,name,is_active) VALUES(:id,:name,true)"), {'id': tenant, 'name': 'selfhost-' + str(tenant)})
                cx.execute(text("""INSERT INTO hypermesh_hardware_classes
                    (id,tenant_id,class_id,vendor,sku,module,memory_gb,public_sku,path_b_suite_id,hourly_rate_cents)
                    VALUES(:id,:tenant,'selfhost-test','test','test','test',1,false,'test',0)"""), {'id': uuid.uuid4(), 'tenant': tenant})
            cx.execute(text(f'SET LOCAL ROLE {role}'))
            for scope in ['', str(uuid.uuid4())]:
                cx.execute(text("SELECT set_config('app.current_tenant_id', :scope, true)"), {'scope': scope})
                for table in tables:
                    # Empty tables still force the RLS expressions through planning.
                    cx.execute(text(f'SELECT count(*) FROM public."{table}"')).scalar_one()
            cx.execute(text("SELECT set_config('app.current_tenant_id', '', true)"))
            assert cx.execute(text('SELECT tenant_id FROM hypermesh_hardware_classes')).all() == []
            for tenant in tenants:
                cx.execute(text("SELECT set_config('app.current_tenant_id', :scope, true)"), {'scope': str(tenant)})
                assert cx.execute(text('SELECT tenant_id FROM hypermesh_hardware_classes')).scalars().all() == [tenant]
            with pytest.raises(DBAPIError):
                with cx.begin_nested():
                    cx.execute(text("UPDATE hypermesh_hardware_classes SET tenant_id=:other"), {'other': tenants[0]})
            cx.execute(text('RESET ROLE'))
    finally:
        with engine.begin() as cx:
            if cx.execute(text('SELECT 1 FROM pg_roles WHERE rolname=:role'), {'role': role}).scalar():
                cx.execute(text(f'DROP OWNED BY {role}'))
                cx.execute(text(f'DROP ROLE {role}'))
        engine.dispose()
