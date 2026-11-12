"""Actual native expiry deletes person-linked risk state without money movement."""

import hashlib
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from controlplane_db import migrations
from migration_test_support import isolated_postgres
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from test_financial_inventory import closed_scope

CALL = text('SELECT payment_erase_expired_payer_risk(:s,:at,:limit)')


@pytest.fixture(scope='module')
def risk_engine():
    with isolated_postgres() as url:
        migrations.upgrade(url, baseline_only=True)
        engine = create_engine(url)
        subjects = {key: str(uuid.uuid4()) for key in ('old', 'reserved', 'unknown', 'other')}
        with engine.begin() as cx:
            root = Path(migrations.__file__).parent / 'migration_chains'
            for chain, revision in (('platform', 'head'), ('hypermesh', 'head'), ('payment_service', 'payment_service_0078_privacy')):
                config = Config()
                config.set_main_option('script_location', str(root))
                config.set_main_option('path_separator', 'os')
                config.set_main_option('version_locations', str(root / chain / 'versions'))
                config.attributes.update(connection=cx, version_table=f'alembic_version_{chain}')
                command.upgrade(config, revision)
            for key, subject in subjects.items():
                cx.execute(text('''INSERT INTO payer_mismatch_accounts
                    (account_key,day,mismatches,reserved_count,reserved_cents,last_mismatch_at)
                    VALUES(:key,'2010-02-28',2,:count,:cents,:observed)'''),
                    {'key': hashlib.sha256(subject.encode()).hexdigest(), 'count': int(key == 'reserved'),
                     'cents': 100 if key == 'reserved' else 0,
                     'observed': None if key == 'unknown' else '2010-02-28T12:00:00Z'})
        migrations.upgrade(url, chains=['platform', 'hypermesh', 'payment_service'])
        with engine.begin() as cx:
            values = {}
            for key, subject in subjects.items():
                v = closed_scope(cx, subject, None)
                cx.execute(text("UPDATE account_lifecycles SET state='deleting' WHERE subject=:s"), v)
                for name in ('account_prime_billing_financial_sources', 'payment_prime_financial_sources', 'hypermesh_prime_financial_sources'):
                    assert cx.scalar(text(f'SELECT {name}(:s,:at,NULL,1000)'), v)['complete']
                values[key] = {**v, 'key': hashlib.sha256(subject.encode()).hexdigest(), 'limit': 100}
        try:
            yield engine, values
        finally:
            engine.dispose()


@pytest.fixture
def risk_transaction(risk_engine):
    engine, values = risk_engine
    with engine.connect() as cx:
        tx = cx.begin()
        try:
            yield cx, values
        finally:
            if tx.is_active:
                tx.rollback()


def test_actual_expiry_deletes_hash_and_bindings_without_tombstones_or_accounting_dimensions(risk_transaction):
    cx, values = risk_transaction
    v = values['old']
    before_other = cx.scalar(text('SELECT to_jsonb(r) FROM payer_mismatch_accounts r WHERE account_key=:key'), values['other'])
    assert cx.scalar(text("SELECT financial_activity_at='2010-02-28T12:00:00Z' AND financial_retain_until='2017-02-28T12:00:00Z' FROM payer_mismatch_accounts WHERE account_key=:key"), v)
    assert cx.scalar(CALL, v) == {'complete': True, 'processed': 1, 'remaining': 0, 'next_due_at': None}
    assert cx.scalar(text('SELECT count(*) FROM payer_mismatch_accounts WHERE account_key=:key'), v) == 0
    assert cx.scalar(text("SELECT count(*) FROM account_financial_source_bindings WHERE owner='payment' AND kind='payer_mismatch_accounts' AND resource=:key"), v) == 0
    assert cx.scalar(text('SELECT count(*) FROM account_financial_transitions')) == 0
    assert cx.scalar(text('SELECT to_jsonb(r) FROM payer_mismatch_accounts r WHERE account_key=:key'), values['other']) == before_other
    assert cx.scalar(CALL, v)['processed'] == 0
    assert cx.scalar(text('SELECT financial_deleted_at FROM account_lifecycles WHERE subject=:s'), v) is None


@pytest.mark.parametrize('key', ['reserved', 'unknown'])
def test_reservations_and_unknown_activity_are_not_zero_proofs(risk_transaction, key):
    cx, values = risk_transaction
    v = values[key]
    before = cx.scalar(text('SELECT to_jsonb(r) FROM payer_mismatch_accounts r WHERE account_key=:key'), v)
    assert cx.scalar(CALL, v) == {'complete': False, 'processed': 0, 'remaining': 1, 'next_due_at': None}
    assert cx.scalar(text('SELECT to_jsonb(r) FROM payer_mismatch_accounts r WHERE account_key=:key'), v) == before


def test_preservation_hold_blocks_due_risk_expiry_even_with_personal_none(risk_transaction, monkeypatch):
    monkeypatch.setenv('ACCOUNT_CLOSURE_RETENTION', 'none')
    cx, values = risk_transaction
    v = values['old']
    cx.execute(text("UPDATE account_lifecycles SET financial_hold=true,hold_reference='preserve' WHERE subject=:s"), v)
    with pytest.raises(DBAPIError) as error, cx.begin_nested():
        cx.scalar(CALL, v)
    assert error.value.orig.sqlstate == '42501'
    assert cx.scalar(text('SELECT count(*) FROM payer_mismatch_accounts WHERE account_key=:key'), v) == 1


def test_native_write_restarts_full_seven_year_clock_and_none_cannot_waive_it(risk_transaction, monkeypatch):
    monkeypatch.setenv('ACCOUNT_CLOSURE_RETENTION', 'none')
    cx, values = risk_transaction
    v = values['old']
    cx.execute(text('UPDATE payer_mismatch_accounts SET mismatches=mismatches+1 WHERE account_key=:key'), v)
    assert cx.scalar(text("SELECT financial_activity_at>transaction_timestamp()-interval '1 minute' AND financial_retain_until=((financial_activity_at AT TIME ZONE 'UTC')+interval '7 years') AT TIME ZONE 'UTC' FROM payer_mismatch_accounts WHERE account_key=:key"), v)
    result = cx.scalar(CALL, v)
    assert result['complete'] is False and result['processed'] == 0 and result['next_due_at'] is not None


@pytest.mark.parametrize('operation', ["DELETE FROM payer_mismatch_accounts WHERE account_key=:key", "UPDATE payer_mismatch_accounts SET financial_retain_until=now()-interval '1 day' WHERE account_key=:key"])
def test_direct_deletion_and_supplied_clock_are_denied(risk_transaction, operation):
    cx, values = risk_transaction
    with pytest.raises(DBAPIError) as error, cx.begin_nested():
        cx.execute(text(operation), values['old'])
    assert error.value.orig.sqlstate == '42501'


def test_real_transaction_rollback_restores_deleted_row_and_bindings(risk_transaction):
    cx, values = risk_transaction
    v = values['old']
    savepoint = cx.begin_nested()
    assert cx.scalar(CALL, v)['processed'] == 1
    savepoint.rollback()
    assert cx.scalar(text('SELECT count(*) FROM payer_mismatch_accounts WHERE account_key=:key'), v) == 1
    assert cx.scalar(text("SELECT count(*) FROM account_financial_source_bindings WHERE owner='payment' AND kind='payer_mismatch_accounts' AND resource=:key"), v) == 1


def test_private_command_is_not_public(risk_transaction):
    cx, _ = risk_transaction
    assert cx.scalar(text("SELECT NOT EXISTS(SELECT 1 FROM pg_proc p,aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a WHERE p.oid='public.payment_erase_expired_payer_risk(text,timestamptz,integer)'::regprocedure AND a.grantee=0 AND a.privilege_type='EXECUTE')"))


def test_every_retained_party_hold_blocks_the_actual_owner_command(risk_transaction):
    cx, values = risk_transaction
    v, other = values['old'], values['other']
    cx.execute(text("SELECT account_bind_financial_source(:parties,NULL,'payment','payer_mismatch_accounts',:key)"),
               {**v, 'parties': [v['s'], other['s']]})
    cx.execute(text("UPDATE account_lifecycles SET financial_hold=true,hold_reference='preserve-other' WHERE subject=:s"), other)
    with pytest.raises(DBAPIError) as error, cx.begin_nested():
        cx.scalar(CALL, v)
    assert error.value.orig.sqlstate == '42501'
    assert cx.scalar(text('SELECT count(*) FROM payer_mismatch_accounts WHERE account_key=:key'), v) == 1


def test_row_first_preservation_update_retries_instead_of_deadlocking(risk_engine):
    engine, values = risk_engine
    v = values['old']
    with engine.connect() as holder, engine.connect() as eraser:
        holder.execute(text('SELECT 1 FROM account_lifecycles WHERE subject=:s FOR UPDATE'), v)
        eraser.execute(text("SET LOCAL statement_timeout='500ms'"))
        with pytest.raises(DBAPIError) as error:
            eraser.scalar(CALL, v)
        assert error.value.orig.sqlstate == '40001'
        eraser.rollback()
        holder.rollback()
        assert eraser.scalar(CALL, v)['processed'] == 1
        eraser.rollback()


@pytest.mark.parametrize('limit', [None, 0, 1001])
def test_invalid_batches_cannot_erase_risk_state(risk_transaction, limit):
    cx, values = risk_transaction
    with pytest.raises(DBAPIError) as error, cx.begin_nested():
        cx.scalar(CALL, {**values['old'], 'limit': limit})
    assert error.value.orig.sqlstate == '42501'
