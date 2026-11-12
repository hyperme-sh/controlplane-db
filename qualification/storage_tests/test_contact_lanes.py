"""Disposable PostgreSQL schema qualification in the nightly batch."""
import importlib.util
import os
from pathlib import Path
import uuid

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError


def test_opaque_lane_schema_bounds_and_isolation():
    raw = os.environ.get('TEST_DATABASE_URL')
    if not raw:
        pytest.fail('CI disposable PostgreSQL is required')
    engine = create_engine(raw)
    schema = 'lanes_' + uuid.uuid4().hex
    path = Path(__file__).resolve().parents[2] / 'src/controlplane_db/migration_chains/platform/versions/0086_contact_lanes.py'
    spec = importlib.util.spec_from_file_location('lane_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    try:
        with engine.begin() as cx:
            cx.execute(text(f'CREATE SCHEMA {schema}'))
            cx.execute(text(f'SET LOCAL search_path TO {schema},public'))
            with Operations.context(MigrationContext.configure(cx)):
                migration.upgrade()
            insert = text("INSERT INTO sociacl_contact_messages (lane_id,message_id,ciphertext,created_at,expires_at) VALUES (:lane,:id,:body,now(),now()+interval '1 day')")
            for lane in ('ab' * 32, 'cd' * 32):
                cx.execute(insert, {'lane': lane, 'id': 'ef' * 32, 'body': b'x' * 32})
            assert cx.execute(text('SELECT count(*) FROM sociacl_contact_messages WHERE lane_id=:lane'), {'lane': 'ab' * 32}).scalar_one() == 1
            for lane, body in [('~pub', b'x' * 32), ('AB' * 32, b'x' * 32), ('12' * 32, b'x' * 31), ('12' * 32, b'x' * 65537)]:
                with pytest.raises(IntegrityError), cx.begin_nested():
                    cx.execute(insert, {'lane': lane, 'id': 'ef' * 32, 'body': body})
            with pytest.raises(IntegrityError), cx.begin_nested():
                cx.execute(text("UPDATE sociacl_contact_messages SET expires_at=created_at+interval '8 days'"))
            columns = cx.execute(text("SELECT column_name FROM information_schema.columns WHERE table_schema=:schema AND table_name='sociacl_contact_messages'"), {'schema': schema}).scalars().all()
            assert not {'tenant_id', 'principal', 'sender', 'recipient', 'owner_id'} & set(columns)
    finally:
        with engine.begin() as cx:
            cx.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        engine.dispose()
