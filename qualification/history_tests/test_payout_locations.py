import uuid
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from alembic import command
import pytest
from controlplane_db import migrations


def test_postal_evidence_rls_and_nonempty_downgrade(migrated_postgres):
    engine = create_engine(migrated_postgres)
    tenant, other, host, revision = [uuid.uuid4() for _ in range(4)]
    role = 'postal_' + uuid.uuid4().hex
    try:
        with engine.begin() as db:
            db.execute(text("INSERT INTO tenants(id,name,is_active) VALUES (:t,'postal-test',true)"), {'t':tenant})
            db.exec_driver_sql(f'CREATE ROLE {role} NOBYPASSRLS')
            db.exec_driver_sql(f'GRANT SELECT, INSERT, UPDATE ON connect_payout_locations TO {role}')
        with engine.begin() as db:
            db.exec_driver_sql(f'SET LOCAL ROLE {role}')
            db.execute(text("SELECT set_config('app.current_tenant_id',:t,true)"), {'t':str(tenant)})
            db.execute(text("INSERT INTO connect_payout_locations(tenant_id,host_org_id,revision,status) VALUES (:t,:h,:r,'pending')"), {'t':tenant,'h':host,'r':revision})
            assert db.scalar(text('SELECT count(*) FROM connect_payout_locations')) == 1
        with engine.begin() as db:
            db.exec_driver_sql(f'SET LOCAL ROLE {role}')
            db.execute(text("SELECT set_config('app.current_tenant_id',:t,true)"), {'t':str(other)})
            assert db.scalar(text('SELECT count(*) FROM connect_payout_locations')) == 0
            assert db.execute(text("UPDATE connect_payout_locations SET status='pending'")).rowcount == 0
        with engine.begin() as db:
            config = migrations._config(migrations._ROOT, 'payment_service', db)
            with pytest.raises(DBAPIError, match='Cannot discard'):
                command.downgrade(config, 'payment_service_0080_fin_state')
    finally:
        with engine.begin() as db:
            db.exec_driver_sql(f'DROP OWNED BY {role}')
            db.exec_driver_sql(f'DROP ROLE {role}')
        engine.dispose()
