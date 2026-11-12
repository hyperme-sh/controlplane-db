"""Owner baselines must equal the actual old-chain 0053 PostgreSQL schema."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import uuid

import pytest
from sqlalchemy import create_engine, text
from alembic.util.exc import CommandError
from alembic import command
from alembic.config import Config

from controlplane_db import migrations
from migration_test_support import isolated_postgres, normalize_sync_sqlalchemy_url, run_alembic_upgrade, alembic_ini_path
from schema_snapshot import schema_snapshot
from contact_lane_contract import assert_contact_lane_delta, assert_same_schema

pytestmark = pytest.mark.integration
CHAINS = migrations._ROOT


def snapshot(url):
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            return schema_snapshot(connection)
    finally:
        engine.dispose()


def execute(url, sql):
    engine = create_engine(url)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(sql, execution_options={'no_parameters': True})
    finally:
        engine.dispose()


@pytest.fixture(scope='module')
def databases():
    with isolated_postgres() as url:
        execute(url, 'CREATE ROLE controlplane; CREATE ROLE controlplane_app NOBYPASSRLS')
        run_alembic_upgrade(url)
        # No source connections may remain when copying its schema and data.
        admin = create_engine(url, isolation_level='AUTOCOMMIT')
        stem = url.rsplit('/', 1)[-1]
        clones = ('fresh', 'stamped', 'wrong_head', 'isolated', 'rollback', 'no_roles', 'reload', 'unversioned', 'reload_old', 'reload_fresh', 'reload_failure', 'marketplace_owners', 'marketplace_legacy', 'marketplace_fresh', 'reload_empty')
        from_source = {'stamped', 'rollback', 'reload', 'reload_failure', 'marketplace_owners', 'marketplace_legacy'}
        with admin.connect() as connection:
            for name in clones:
                template = stem if name in from_source else 'template0'
                connection.exec_driver_sql(f'CREATE DATABASE "{stem}_{name}" TEMPLATE "{template}"')
        admin.dispose()
        base = url.rsplit('/', 1)[0]
        yielded = {'source': url}
        yielded.update({name: f'{base}/{stem}_{name}' for name in clones})
        yield yielded


def test_fresh_baselines_match_every_0053_database_object(databases):
    migrations.upgrade(databases['fresh'], baseline_only=True)
    expected, actual = snapshot(databases['source']), snapshot(databases['fresh'])
    differences = {name: {field: [expected['tables'].get(name, {}).get(field), value]
                         for field, value in table.items()
                         if expected['tables'].get(name, {}).get(field) != value}
                   for name, table in actual['tables'].items() if expected['tables'].get(name) != table}
    assert actual == expected, json.dumps(differences, indent=2)
    assert len(actual['tables']) == 80
    assert 'hypermesh_onboarding_runs' in actual['tables']
    assert len(actual['functions']) == 7
    assert migrations.current_heads(databases['fresh']) == {name: entry['baseline'] for name, entry in json.loads((CHAINS/'manifest.json').read_text())['chains'].items()}
    # Fresh baselines contain schema, not the private old-chain seed data.
    engine = create_engine(databases['fresh'])
    with engine.connect() as connection:
        assert connection.execute(text('SELECT count(*) FROM tenants')).scalar_one() == 0
    engine.dispose()


def test_stamp_then_upgrade_preserves_schema_and_existing_data(databases):
    url = databases['stamped']
    identity = str(uuid.uuid4())
    execute(url, f"INSERT INTO tenants (id,name,is_active) VALUES ('{identity}', 'baseline-preservation-test',false)")
    before = snapshot(url)
    migrations.stamp_baselines(url)
    migrations.upgrade(url, baseline_only=True)
    migrations.stamp_baselines(url)  # Idempotent only while every owner is at baseline.
    assert snapshot(url) == before
    engine = create_engine(url)
    with engine.connect() as connection:
        assert connection.execute(text('SELECT name FROM tenants WHERE id=:id'), {'id': identity}).scalar_one() == 'baseline-preservation-test'
        assert connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one() == '0053_onboarding_runs'
    engine.dispose()


def test_other_mixed_revisions_cannot_be_stamped_or_implicitly_upgraded(databases, monkeypatch):
    url = databases['wrong_head']
    monkeypatch.setenv('DATABASE_URL', url)
    command.upgrade(Config(str(alembic_ini_path())), '0052_host_registrations')
    before = snapshot(url)
    with pytest.raises(ValueError, match='0053_onboarding_runs'):
        migrations.stamp_baselines(url)
    with pytest.raises(ValueError, match='explicit 0053'):
        migrations.upgrade(url)
    assert snapshot(url) == before
    assert set(migrations.current_heads(url).values()) == {None}
    run_alembic_upgrade(url)
    migrations.stamp_baselines(url)
    registry = json.loads((CHAINS / 'manifest.json').read_text())
    assert migrations.current_heads(url) == {chain: entry['baseline'] for chain, entry in registry['chains'].items()}
    assert snapshot(url) == snapshot(databases['source'])


def test_product_migration_changes_only_its_owner_head(databases, tmp_path):
    root = tmp_path / 'chains'
    shutil.copytree(CHAINS, root)
    migrations.upgrade(databases['isolated'], registry_path=root)
    before = migrations.current_heads(databases['isolated'], root)
    (root / 'hypermesh/versions/0054_test.py').write_text('''from alembic import op
revision = "hypermesh_planted_0054"
down_revision = "CURRENT_HEAD"
branch_labels = None
depends_on = None
def upgrade():
    op.execute("ALTER TABLE hypermesh_devices ADD COLUMN planted_test integer")
def downgrade():
    op.execute("ALTER TABLE hypermesh_devices DROP COLUMN planted_test")
'''.replace('CURRENT_HEAD', before['hypermesh']))
    migrations.upgrade(databases['isolated'], chains=['hypermesh'], registry_path=root)
    after = migrations.current_heads(databases['isolated'], root)
    assert after['hypermesh'] == 'hypermesh_planted_0054'
    assert {k:v for k,v in after.items() if k != 'hypermesh'} == {k:v for k,v in before.items() if k != 'hypermesh'}
    assert snapshot(databases['source']) != snapshot(databases['isolated'])


def test_failure_rolls_back_every_stamp_table(databases, tmp_path):
    root = tmp_path / 'chains'
    shutil.copytree(CHAINS, root)
    # A nonexistent last revision causes failure after earlier commands issued.
    registry = json.loads((root/'manifest.json').read_text())
    registry['chains']['payment_service']['baseline'] = 'missing_baseline'
    (root/'manifest.json').write_text(json.dumps(registry))
    with pytest.raises(CommandError, match="missing_baseline"):
        migrations.stamp_baselines(databases['rollback'], root)
    assert set(migrations.current_heads(databases['rollback']).values()) == {None}


def test_schema_diff_detects_rls_index_constraint_and_grant_drift(databases):
    url = databases['isolated']
    before = snapshot(url)
    execute(url, "ALTER TABLE hypermesh_devices DISABLE ROW LEVEL SECURITY; "
                 "CREATE INDEX planted_tenant_idx ON hypermesh_devices(tenant_id); "
                 "ALTER TABLE hypermesh_devices ADD CONSTRAINT planted_check CHECK (id IS NOT NULL); "
                 "GRANT SELECT ON hypermesh_devices TO controlplane_app")
    after = snapshot(url)
    for key in ('rls', 'indexes', 'constraints', 'grants'):
        assert before['tables']['hypermesh_devices'][key] != after['tables']['hypermesh_devices'][key]


def test_baselines_match_when_optional_app_roles_do_not_exist(migration_database):
    # The shared migration server is checked to have no controlplane/controlplane_app roles.
    url = migration_database('head')
    fresh = migration_database()
    migrations.upgrade(fresh, baseline_only=True)
    assert snapshot(url) == snapshot(fresh)


def test_cross_chain_foreign_keys_only_target_platform(databases):
    registry = json.loads((CHAINS/'manifest.json').read_text())
    owners = {table: chain for chain, entry in registry['chains'].items() for table in entry['tables']}
    engine = create_engine(databases['source'])
    with engine.connect() as connection:
        pairs = connection.execute(text("""SELECT child.relname,parent.relname FROM pg_constraint k
            JOIN pg_class child ON child.oid=k.conrelid JOIN pg_class parent ON parent.oid=k.confrelid
            JOIN pg_namespace n ON n.oid=child.relnamespace
            WHERE k.contype='f' AND n.nspname='public'""")).all()
    engine.dispose()
    for child, parent in pairs:
        assert owners[child] == owners[parent] or owners[parent] == 'platform'


def test_empty_or_partial_databases_cannot_be_stamped(databases):
    with pytest.raises(ValueError, match='0053_onboarding_runs'):
        migrations.stamp_baselines(databases['no_roles'])
    execute(databases['no_roles'], "CREATE TABLE alembic_version(version_num varchar(32)); "
            "INSERT INTO alembic_version VALUES ('0053_onboarding_runs')")
    with pytest.raises(ValueError, match='missing baseline tables'):
        migrations.stamp_baselines(databases['no_roles'])
    assert set(migrations.current_heads(databases['no_roles']).values()) == {None}


def test_reload_adopts_existing_database_and_is_repeatable(databases, tmp_path):
    from controlplane_db.startup import _owners
    url = databases['reload']
    before = snapshot(url)
    migrations.prepare_event_source_index(url)
    _owners(url)
    _owners(url)
    assert migrations.current_heads(url) == migrations.chain_heads()
    after = snapshot(url)
    assert_payment_financial_schema_delta(after)
    assert after['tables'].pop('host_payout_addresses')['rls'] == [True, True]
    assert_journal_schema_delta(after)
    assert_hypermesh_empty_scope_delta(before, after)
    assert_subject_scope_delta(before, after)
    assert_cache_migration_delta(before, after)
    root = tmp_path / 'chains'
    shutil.copytree(CHAINS, root)
    (root / 'payment_service/versions/0054_reload.py').write_text(f"""from alembic import op
revision = 'payment_reload_0054'
down_revision = '{migrations.chain_heads()["payment_service"]}'
branch_labels = None
depends_on = None
def upgrade():
    op.execute('CREATE TABLE payment_reload_marker(id integer)')
def downgrade():
    pass
""")
    _owners(url, root)
    _owners(url, root)
    assert migrations.current_heads(url, root)['payment_service'] == 'payment_reload_0054'


def test_reload_refuses_unversioned_existing_schema(databases):
    from controlplane_db.startup import _owners
    url = databases['unversioned']
    execute(url, 'CREATE TABLE tenants (id uuid PRIMARY KEY)')
    before = snapshot(url)
    with pytest.raises(ValueError, match='unversioned existing'):
        _owners(url)
    assert snapshot(url) == before


def test_reload_refuses_0052_without_changing_it(databases, monkeypatch):
    from controlplane_db.startup import _owners
    url = databases['reload_old']
    monkeypatch.setenv('DATABASE_URL', url)
    command.upgrade(Config(str(alembic_ini_path())), '0052_host_registrations')
    before = snapshot(url)
    with pytest.raises(ValueError, match='0053_onboarding_runs'):
        _owners(url)
    assert snapshot(url) == before
    assert set(migrations.current_heads(url).values()) == {None}


def test_reload_fresh_database_uses_owner_schema(databases):
    from controlplane_db.startup import _owners
    _owners(databases['reload_fresh'], allow_empty=True)
    after = snapshot(databases['reload_fresh'])
    assert_payment_financial_schema_delta(after)
    assert after['tables'].pop('host_payout_addresses')['rls'] == [True, True]
    assert_journal_schema_delta(after)
    before = snapshot(databases['source'])
    assert_hypermesh_empty_scope_delta(before, after)
    assert_subject_scope_delta(before, after)
    assert_cache_migration_delta(before, after)
    assert migrations.current_heads(databases['reload_fresh']) == migrations.chain_heads()


def test_reload_refuses_empty_database_without_bootstrap(databases, monkeypatch):
    from controlplane_db.startup import _owners
    monkeypatch.delenv('CONTROLPLANE_DB_BOOTSTRAP', raising=False)
    url = databases['reload_empty']
    before = snapshot(url)
    with pytest.raises(ValueError, match='refusing to create one'):
        _owners(url)
    assert snapshot(url) == before
    assert set(migrations.current_heads(url).values()) == {None}


def test_reload_upgrade_failure_rolls_back_adoption(databases, tmp_path):
    from controlplane_db.startup import _owners
    root = tmp_path / 'chains'
    shutil.copytree(CHAINS, root)
    (root / 'payment_service/versions/0054_failure.py').write_text(f"""from alembic import op
revision = 'payment_failure_0054'
down_revision = '{migrations.chain_heads()["payment_service"]}'
branch_labels = None
depends_on = None
def upgrade():
    op.execute('CREATE TABLE reload_failure_marker(id integer)')
    raise RuntimeError('planted reload failure')
def downgrade():
    pass
""")
    url = databases['reload_failure']
    migrations.prepare_event_source_index(url)
    before = snapshot(url)
    with pytest.raises(RuntimeError, match='planted reload failure'):
        _owners(url, root)
    assert snapshot(url) == before
    assert set(migrations.current_heads(url).values()) == {None}




def assert_hypermesh_financial_schema_delta(after):
    clock_tables = {'hypermesh_leases','hypermesh_payouts','hypermesh_orders','hypermesh_fills'}
    source_tables = clock_tables | {'hypermesh_jobs','hypermesh_tunnels','hypermesh_tickets','host_organization_bindings'}
    for name in source_tables:
        table = after['tables'][name]
        for trigger_name, event, function in (
            ('account_financial_epoch','AFTER INSERT OR DELETE OR UPDATE','hypermesh_account_financial_epoch()'),
            ('account_financial_not_truncated','BEFORE TRUNCATE','account_refuse_financial_truncate()'),
        ):
            trigger = next(t for t in table['triggers'] if t[0]==trigger_name)
            assert event in trigger[1] and function in trigger[1] and trigger[2]=='O'
            table['triggers'].remove(trigger)
        if name in clock_tables:
            columns = [c for c in table['columns'] if c[0] in {'financial_activity_at','financial_retain_until'}]
            assert [(c[0],c[1],c[2]) for c in columns] == [
                ('financial_activity_at','timestamp with time zone',False),
                ('financial_retain_until','timestamp with time zone',False)]
            table['columns'] = [c for c in table['columns'] if c not in columns]
            constraint = next(c for c in table['constraints'] if c[0]=='ck_'+name+'_financial_clock')
            table['constraints'].remove(constraint)
            index = next(i for i in table['indexes'] if i[0]=='ix_'+name+'_financial_due')
            table['indexes'].remove(index)
            trigger = next(t for t in table['triggers'] if t[0]=='account_financial_clock')
            assert 'BEFORE INSERT OR UPDATE' in trigger[1] and 'hypermesh_financial_clock()' in trigger[1]
            table['triggers'].remove(trigger)
    for runtime_table in ('hypermesh_jobs', 'hypermesh_tunnels'):
        triggers = after['tables'][runtime_table]['triggers']
        runtime_trigger = next(t for t in triggers if t[0] == 'account_runtime_admission')
        assert 'BEFORE INSERT OR UPDATE' in runtime_trigger[1]
        assert 'hypermesh_personal_runtime_admission()' in runtime_trigger[1]
        triggers.remove(runtime_trigger)
    reviewers = after['tables']['hypermesh_devices']['triggers']
    reviewer = next(t for t in reviewers if t[0] == 'account_reviewer_admission')
    assert 'BEFORE INSERT OR UPDATE' in reviewer[1]
    assert 'hypermesh_device_reviewer_admission()' in reviewer[1]
    reviewers.remove(reviewer)
    approvals = after['tables']['hypermesh_onboarding_runs']['triggers']
    approval = next(t for t in approvals if t[0] == 'account_approval_admission')
    assert 'BEFORE INSERT OR UPDATE ON public.hypermesh_onboarding_runs' in approval[1]
    assert 'hypermesh_personal_approval_admission()' in approval[1] and approval[2] == 'O'
    approvals.remove(approval)
    for signature in ('hypermesh_account_financial_state(p_subject text, p_closed_at timestamp with time zone)',
                      'hypermesh_financial_clock()',
                      'hypermesh_financial_parties(p_table text, p_source jsonb)',
                      'hypermesh_account_financial_epoch()',
                      'hypermesh_prime_financial_sources(p_subject text, p_closed_at timestamp with time zone, p_tenant uuid, p_limit integer)',
                      'hypermesh_erase_personal_host_associations(p_subject text, p_closed_at timestamp with time zone, p_tenant uuid, p_limit integer)',
                      'hypermesh_personal_approval_admission()',
                      'hypermesh_device_reviewer_admission()',
                      'hypermesh_erase_personal_device_reviewers(p_subject text, p_closed_at timestamp with time zone, p_tenant uuid, p_limit integer)',
                      'hypermesh_personal_runtime_admission()',
                      'hypermesh_personal_model_wait(p_subject text, p_tenant uuid, p_model_closed_at timestamp with time zone)',
                      'hypermesh_erase_personal_runtime(p_subject text, p_closed_at timestamp with time zone, p_tenant uuid, p_limit integer)'):
        function = after['functions'].pop(signature)
        assert 'SECURITY DEFINER' in function['definition']
        assert "search_path TO 'pg_catalog'" in function['definition']
        assert function['grants'] == [['OWNER','EXECUTE',False]]
        if signature != 'hypermesh_financial_clock()':
            assert "row_security TO 'off'" in function['definition']


def assert_cache_migration_delta(before, after):
    assert_hypermesh_financial_schema_delta(after)
    totals = after['tables'].pop('financial_accounting_totals')
    assert [(c[0], c[1], c[2]) for c in totals['columns']] == [
        ('metric', 'character varying(32)', True),
        ('currency', 'character varying(4)', True),
        ('unit', 'character varying(16)', True),
        ('amount', 'numeric(78,0)', True),
    ]
    assert totals['rls'] == [False, False]
    assert not totals['policies'] and not totals['column_grants']
    assert {t[0] for t in totals['triggers']} == {'financial_totals_preserved', 'financial_totals_not_truncated'}
    assert all('account_preserve_anonymous_totals()' in t[1] and t[2] == 'O' for t in totals['triggers'])
    preserve = after['functions'].pop('account_preserve_anonymous_totals()')
    assert "search_path TO 'pg_catalog'" in preserve['definition']
    assert preserve['grants'] == [['OWNER', 'EXECUTE', False]]
    assert all(grant[0] == 'OWNER' for grant in totals['grants'])
    assert {c[0] for c in totals['constraints']} == {
        'financial_accounting_totals_pkey', 'ck_financial_total_metric', 'ck_financial_total_unit',
    }
    assert any(c[1] == 'p' and c[2] == 'PRIMARY KEY (metric, currency, unit)' for c in totals['constraints'])
    for signature in ('account_billing_financial_metadata(p_metadata jsonb)',
                      'account_billing_financial_clock()',
                      'account_assert_financial_clock_removable()'):
        clock_function = after['functions'].pop(signature)
        assert "search_path TO 'pg_catalog'" in clock_function['definition']
        assert clock_function['grants'] == [['OWNER', 'EXECUTE', False]]
        if signature != 'account_billing_financial_metadata(p_metadata jsonb)':
            assert 'SECURITY DEFINER' in clock_function['definition']
        if signature == 'account_billing_financial_clock()':
            assert clock_function['definition'].count("'stripe_livemode'")==2
            assert "interval '7 years'" in clock_function['definition']
    billing = after['tables']['billing_records']
    added_columns = [c for c in billing['columns'] if c[0] in {'financial_activity_at', 'financial_retain_until'}]
    assert [(c[0], c[1], c[2], c[3]) for c in added_columns] == [
        ('financial_activity_at', 'timestamp with time zone', True, None),
        ('financial_retain_until', 'timestamp with time zone', True, None),
    ]
    billing['columns'] = [c for c in billing['columns'] if c not in added_columns]
    clock_index = next(i for i in billing['indexes'] if i[0] == 'ix_billing_financial_due')
    assert '(financial_retain_until, id)' in clock_index[1]
    billing['indexes'].remove(clock_index)
    clock_trigger = next(t for t in billing['triggers'] if t[0] == 'billing_financial_clock')
    assert 'BEFORE INSERT OR UPDATE ON public.billing_records' in clock_trigger[1]
    assert 'account_billing_financial_clock()' in clock_trigger[1]
    assert clock_trigger[2] == 'O'
    billing['triggers'].remove(clock_trigger)
    transitions = after['tables'].pop('account_financial_transitions')
    assert {c[0] for c in transitions['columns']} == {
        'id','transaction_id','owner','kind','resource','before_digest','after_digest'}
    assert transitions['rls'] == [True, True]
    assert not transitions['policies'] and not transitions['column_grants']
    assert all(grant[0] == 'OWNER' for grant in transitions['grants'])
    assert len(transitions['triggers']) == 1
    assert 'DEFERRABLE INITIALLY DEFERRED' in transitions['triggers'][0][1]
    assert 'account_financial_transition_ephemeral()' in transitions['triggers'][0][1]
    source_bindings = after['tables'].pop('account_financial_source_bindings')
    assert {c[0] for c in source_bindings['columns']} == {'id','subject','tenant_id','owner','kind','resource'}
    assert source_bindings['rls'] == [True, True]
    assert len(source_bindings['triggers']) == 1
    assert source_bindings['triggers'][0][0] == 'financial_bindings_not_truncated'
    assert len(source_bindings['policies']) == 1
    assert not source_bindings['column_grants']
    assert all(grant[0] == 'OWNER' for grant in source_bindings['grants'])
    fence_registry = after['tables'].pop('account_financial_fence_versions')
    assert {c[0] for c in fence_registry['columns']} == {'owner', 'protocol'}
    assert fence_registry['rls'] == [False, False]
    assert not fence_registry['policies'] and not fence_registry['column_grants']
    assert all(grant[0] == 'OWNER' for grant in fence_registry['grants'])
    budget_creators = after['tables']['crypto_agent_budgets']['triggers']
    budget_fence = next(t for t in budget_creators if t[0] == 'aaa_budget_creator_fence')
    assert 'BEFORE UPDATE' in budget_fence[1] and 'account_budget_creator_fence()' in budget_fence[1]
    budget_creators.remove(budget_fence)
    paid_creator = after['tables']['subscription_plans']['triggers']
    paid_trigger = next(t for t in paid_creator if t[0] == 'aaa_paid_plan_creator')
    assert 'BEFORE INSERT OR UPDATE' in paid_trigger[1]
    assert 'account_paid_plan_creator()' in paid_trigger[1]
    paid_creator.remove(paid_trigger)
    for signature in (
        'account_native_financial_state(p_subject text, p_closed_at timestamp with time zone, p_owner text)',
        'account_billing_financial_state(p_subject text, p_closed_at timestamp with time zone)',
        'account_finish_source_free_closure(p_subject text, p_closed_at timestamp with time zone, p_expected_epoch bigint)',
        'account_check_closure_worker_installation()',
        'account_unbind_expired_payer_risk(p_before jsonb)',
        'account_personal_profile_ids(p_subject text, p_tenant uuid)',
        'account_erase_personal_company_creators(p_subject text, p_closed_at timestamp with time zone, p_tenant uuid, p_limit integer)',
        'account_budget_creator_fence()',
        'account_paid_plan_creator()',
        'account_lock_personal_access_actor(p_subject text, p_tenant uuid)',
        'account_unbind_personal_access_actor(p_subject text, p_tenant uuid, p_grant uuid)',
        'account_lock_financial_gc_parties(p_subject text, p_closed_at timestamp with time zone, p_tenant uuid, p_parties text[], p_expected_epoch bigint)',
        'account_merge_anonymous_total(p_metric text, p_currency text, p_unit text, p_amount numeric)',
        'account_financial_transition_ephemeral()',
        'account_issue_financial_transition(p_subject text, p_closed_at timestamp with time zone, p_tenant uuid, p_parties text[], p_owner text, p_kind text, p_resource text, p_before jsonb, p_after jsonb, p_expected_epoch bigint)',
        'account_financial_transition_allowed(p_owner text, p_kind text, p_resource text, p_before jsonb, p_after jsonb)',
        'account_finish_financial_transition(p_capability uuid)',
        'account_personal_model_erasure_allowed(p_subject text, p_tenant uuid, p_model_closed_at timestamp with time zone)',
        'account_mark_personal_runtime_erased(p_subject text, p_tenant uuid)',
        'account_require_runtime_lease_reference(p_tenant uuid, p_lease uuid)',
        'account_personal_renter_leases(p_subject text, p_tenant uuid)',
        'account_require_personal_erasure(p_subject text, p_tenant uuid)',
        'account_unbind_hypermesh_personal_sources(p_subject text, p_tenant uuid)',
        'account_require_financial_inventory(p_subject text, p_closed_at timestamp with time zone)',
        'account_lock_financial_inventory_schema()',
        'account_lock_financial_inventory(p_subject text, p_closed_at timestamp with time zone, p_tenant_id uuid)',
        'account_financial_source_bound(p_subject text, p_tenant uuid, p_owner text, p_kind text, p_resource text)',
        'account_record_financial_inventory(p_subject text, p_closed_at timestamp with time zone, p_tenant uuid, p_owner text)',
        'account_prime_billing_financial_sources(p_subject text, p_closed_at timestamp with time zone, p_tenant uuid, p_limit integer)',
        'account_touch_financial_subjects(p_subjects text[], p_recapture_subjects text[])',
        'account_financial_epoch(p_subject text, p_closed_at timestamp with time zone, p_tenant_id uuid, p_expected bigint, p_owners text[])',
        'account_billing_financial_epoch()',
        'account_refuse_financial_truncate()',
        'account_billing_financial_source(p_id uuid, p_tenant uuid)',
        'account_bind_financial_source(p_subjects text[], p_tenant uuid, p_owner text, p_kind text, p_resource text)',
        'account_lock_financial_fence_changes()',
        'account_register_financial_fence(p_owner text, p_protocol integer)',
        'account_unregister_financial_fence(p_owner text)',
        'account_financial_parties(p_person uuid, p_actor text, p_tenant uuid, p_owner text, p_kind text, p_resource text, p_actor_hash text)',
    ):
        epoch_function = after['functions'].pop(signature)
        assert 'SECURITY DEFINER' in epoch_function['definition']
        assert "search_path TO 'pg_catalog'" in epoch_function['definition']
        assert "row_security TO 'off'" in epoch_function['definition']
        assert epoch_function['grants'] == [['OWNER', 'EXECUTE', False]]
    epoch_trigger = next(t for t in billing['triggers'] if t[0] == 'billing_financial_epoch')
    assert 'AFTER INSERT OR DELETE OR UPDATE ON public.billing_records' in epoch_trigger[1]
    assert 'account_billing_financial_epoch()' in epoch_trigger[1]
    assert epoch_trigger[2] == 'O'
    billing['triggers'].remove(epoch_trigger)
    truncate_trigger = next(t for t in billing['triggers'] if t[0]=='billing_financial_not_truncated')
    assert 'BEFORE TRUNCATE' in truncate_trigger[1] and 'account_refuse_financial_truncate()' in truncate_trigger[1]
    billing['triggers'].remove(truncate_trigger)
    financial = after['functions'].pop('account_lock_financial_erasure(p_subject text, p_closed_at timestamp with time zone, p_tenant_id uuid)')
    assert 'SECURITY DEFINER' in financial['definition']
    assert "search_path TO 'pg_catalog'" in financial['definition']
    assert 'pg_advisory_xact_lock' in financial['definition']
    assert 'NOT a.financial_hold' in financial['definition']
    assert financial['grants'] == [['OWNER', 'EXECUTE', False]]
    hold = after['functions'].pop('account_serialize_financial_hold()')
    assert 'pg_advisory_xact_lock' in hold['definition']
    assert "search_path TO 'pg_catalog'" in hold['definition']
    assert hold['grants'] == [['OWNER', 'EXECUTE', False]]
    triggers = after['tables']['account_lifecycles']['triggers']
    trigger = next(t for t in triggers if t[0] == 'account_financial_hold_serialized')
    assert 'BEFORE UPDATE ON public.account_lifecycles' in trigger[1]
    assert 'account_serialize_financial_hold()' in trigger[1]
    assert trigger[2] == 'O'
    triggers.remove(trigger)
    for signature in (
        'account_require_open_subjects(p_subjects text[])',
        'account_subjects_for_person(p_person uuid)',
        'platform_account_admission()',
        'account_assert_guards_removable()',
    ):
        admission = after['functions'].pop(signature)
        assert 'SECURITY DEFINER' in admission['definition']
        assert "search_path TO 'pg_catalog'" in admission['definition']
        assert admission['grants'] == [['OWNER', 'EXECUTE', False]]
    reference = after['functions'].pop('platform_person_reference_admission()')
    assert 'SECURITY DEFINER' in reference['definition']
    assert "search_path TO 'pg_catalog'" in reference['definition']
    assert "row_security TO 'off'" in reference['definition']
    assert reference['grants'] == [['OWNER', 'EXECUTE', False]]
    for table in ('crypto_agent_budgets', 'subscription_plans', 'user_preferences',
                  'user_group_memberships', 'chat_sessions_ai'):
        triggers = after['tables'][table]['triggers']
        trigger = next(t for t in triggers if t[0] == 'account_person_reference_admission')
        assert 'BEFORE INSERT OR UPDATE ON public.' + table in trigger[1]
        assert 'platform_person_reference_admission()' in trigger[1]
        assert trigger[2] == 'O'
        triggers.remove(trigger)
    auth = after['functions'].pop('platform_auth_artifact_admission()')
    assert 'SECURITY DEFINER' in auth['definition']
    assert "search_path TO 'pg_catalog'" in auth['definition']
    assert "row_security TO 'off'" in auth['definition']
    assert auth['grants'] == [['OWNER', 'EXECUTE', False]]
    for table in ('user_wallet_bindings', 'user_password_resets', 'user_magic_links'):
        triggers = after['tables'][table]['triggers']
        trigger = next(t for t in triggers if t[0] == 'account_auth_admission')
        assert 'AFTER INSERT OR UPDATE ON public.' + table in trigger[1]
        assert 'platform_auth_artifact_admission()' in trigger[1]
        assert trigger[2] == 'O'
        triggers.remove(trigger)
    for table, name in (('users', 'account_user_admission'), ('api_keys', 'account_key_admission')):
        triggers = after['tables'][table]['triggers']
        trigger = next(t for t in triggers if t[0] == name)
        assert 'AFTER INSERT OR UPDATE ON public.' + table in trigger[1]
        assert 'platform_account_admission()' in trigger[1]
        assert trigger[2] == 'O'
        triggers.remove(trigger)
    product_admission = after['functions'].pop('hypermesh_account_admission()')
    assert 'SECURITY DEFINER' in product_admission['definition']
    assert "search_path TO 'pg_catalog'" in product_admission['definition']
    assert product_admission['grants'] == [['OWNER', 'EXECUTE', False]]
    for table in ('hypermesh_leases', 'hypermesh_tickets', 'hypermesh_devices',
                  'host_organization_bindings', 'hypermesh_model_revisions',
                  'hypermesh_model_validations', 'hypermesh_host_registrations'):
        triggers = after['tables'][table]['triggers']
        trigger = next(t for t in triggers if t[0] == 'account_admission')
        assert 'AFTER INSERT OR UPDATE ON public.' + table in trigger[1]
        assert 'hypermesh_account_admission()' in trigger[1]
        assert trigger[2] == 'O'
        triggers.remove(trigger)
    owner_triggers = after['tables']['host_organization_bindings']['triggers']
    owner_delete = next(t for t in owner_triggers if t[0] == 'account_owner_delete')
    assert 'BEFORE DELETE ON public.host_organization_bindings' in owner_delete[1]
    assert 'hypermesh_account_admission()' in owner_delete[1]
    assert owner_delete[2] == 'O'
    owner_triggers.remove(owner_delete)
    for name, columns, scoped in (
        ('account_lifecycles', {'subject','requested_at','requested_by','source','state','closed_at',
            'profile_deleted_at','financial_deleted_at','financial_retain_until','financial_epoch','financial_hold',
            'hold_reference','claim_id','claim_until','retry_at','last_error','effects'}, False),
        ('account_lifecycle_scopes', {'tenant_id','subject','user_ids','effects'}, True),
        ('api_key_owner_closures', {'tenant_id','subject','closed_at'}, True),
        ('identity_retirements', {'subject','retired_at'}, False),
    ):
        lifecycle = after['tables'].pop(name)
        assert {c[0] for c in lifecycle['columns']} == columns
        assert lifecycle['rls'] == [scoped, scoped]
        assert len(lifecycle['policies']) == int(scoped)
        assert not lifecycle['triggers'] and not lifecycle['column_grants']
        assert all(grant[0] == 'OWNER' for grant in lifecycle['grants'])
        constraints = {c[0]:c[2] for c in lifecycle['constraints']}
        assert constraints[name + '_pkey'] == ('PRIMARY KEY (tenant_id, subject)' if scoped else 'PRIMARY KEY (subject)')
        if scoped:
            assert 'app.current_tenant_id' in lifecycle['policies'][0][4]
            assert 'app.current_tenant_id' in lifecycle['policies'][0][5]
            assert 'ON DELETE RESTRICT' in constraints[name + '_tenant_id_fkey']
        if name == 'account_lifecycles':
            assert {'ck_account_lifecycle_subject', 'ck_account_lifecycle_state'} <= constraints.keys()
            assert any(index[0] == 'ix_account_lifecycle_work' for index in lifecycle['indexes'])
    for table, columns in {
        'hypermesh_history_preferences': {'tenant_id','subject','enabled','generation','consent_at','collect_after','closed_at','purged_at'},
        'hypermesh_history_entries': {'id','tenant_id','subject','created_at','prompt','output','media_type'},
        'hypermesh_history_audit': {'id','tenant_id','subject','actor','action','deleted_count','created_at'},
    }.items():
        history = after['tables'].pop(table)
        assert history['rls'] == [True, True]
        assert {c[0] for c in history['columns']} == columns
        assert len(history['policies']) == 1
        assert 'app.current_tenant_id' in history['policies'][0][4]
        assert 'app.current_tenant_id' in history['policies'][0][5]
    for table in ('hypermesh_training_consents', 'hypermesh_training_submissions', 'hypermesh_training_deletions'):
        training = after['tables'].pop(table)
        assert training['rls'] == [True, True]
        expected_columns = {
            'hypermesh_training_consents': {'tenant_id', 'subject', 'enabled', 'generation', 'consent_at', 'collect_after'},
            'hypermesh_training_submissions': {'id', 'tenant_id', 'subject', 'consent_at', 'created_at', 'prompt', 'output', 'media_type'},
            'hypermesh_training_deletions': {'id', 'tenant_id', 'subject', 'actor', 'deleted_count', 'created_at'},
        }
        assert {column[0] for column in training['columns']} == expected_columns[table]
        if table == 'hypermesh_training_consents':
            assert any(c[0] == 'ck_training_consent_time' and 'collect_after IS NOT NULL' in c[2] for c in training['constraints'])
        assert len(training['policies']) == 1
        assert 'app.current_tenant_id' in training['policies'][0][4]
        assert 'app.current_tenant_id' in training['policies'][0][5]
    requests = after['tables'].pop('account_closure_requests')
    assert requests['rls'] == [True, True]
    assert {c[0] for c in requests['columns']} == {
        'tenant_id', 'subject', 'requested_at', 'requested_by', 'source',
    }
    assert len(requests['policies']) == 1
    assert 'app.current_tenant_id' in requests['policies'][0][4]
    assert 'app.current_tenant_id' in requests['policies'][0][5]
    constraints = {c[0]: c[2] for c in requests['constraints']}
    assert constraints['account_closure_requests_pkey'] == 'PRIMARY KEY (tenant_id, subject)'
    assert 'ON DELETE RESTRICT' in constraints['account_closure_requests_tenant_id_fkey']
    assert {'ck_account_closure_source', 'ck_account_closure_subject', 'ck_account_closure_actor'} <= constraints.keys()
    assert any(c[0] == 'ix_account_closure_requested' for c in requests['indexes'])
    replay = after['tables'].pop('sociacl_checkpoint_requests')
    assert [(c[0], c[1], c[2]) for c in replay['columns']] == [
        ('request_hash', 'character varying(64)', True), ('consumed_at', 'bigint', True),
    ]
    replay_constraints = {c[0]: c[2] for c in replay['constraints']}
    assert set(replay_constraints) == {'sociacl_checkpoint_requests_pkey',
        'ck_checkpoint_request_hash', 'ck_checkpoint_consumed_at'}
    assert replay_constraints['sociacl_checkpoint_requests_pkey'] == 'PRIMARY KEY (request_hash)'
    assert '^[0-9a-f]{64}$' in replay_constraints['ck_checkpoint_request_hash']
    assert '9007199254740991' in replay_constraints['ck_checkpoint_consumed_at']
    assert replay['rls'] == [False, False]
    assert not replay['policies'] and not replay['triggers'] and not replay['column_grants']
    assert all(grant[0] == 'OWNER' for grant in replay['grants'])
    policy = after['tables'].pop('sociacl_witness_policy')
    assert [(c[0], c[1], c[2]) for c in policy['columns']] == [
        ('id', 'integer', True), ('revision', 'bigint', True),
        ('jwks', 'jsonb', True), ('history', 'jsonb', True),
    ]
    policy_constraints = {c[0]: c[2] for c in policy['constraints']}
    assert set(policy_constraints) == {'sociacl_witness_policy_pkey', 'ck_sociacl_policy_singleton', 'ck_sociacl_policy_revision'}
    assert policy_constraints['sociacl_witness_policy_pkey'] == 'PRIMARY KEY (id)'
    assert 'id = 1' in policy_constraints['ck_sociacl_policy_singleton']
    assert '9007199254740991' in policy_constraints['ck_sociacl_policy_revision']
    assert policy['rls'] == [False, False]
    assert not policy['policies'] and not policy['triggers'] and not policy['column_grants']
    assert all(grant[0] == 'OWNER' for grant in policy['grants'])
    state = after['tables'].pop('sociacl_keyring_state')
    assert [(c[0], c[1], c[2]) for c in state['columns']] == [
        ('principal', 'character varying(87)', True),
        ('head_floor', 'bigint', True),
        ('recovery_generation', 'bigint', True),
        ('wrap_generation', 'bigint', True),
        ('recovery', 'bytea', True),
        ('wraps', 'bytea', True),
    ]
    constraints = {c[0]: c[2] for c in state['constraints']}
    assert set(constraints) == {
        'sociacl_keyring_state_pkey', 'ck_sociacl_keyring_principal',
        'ck_sociacl_keyring_floor', 'ck_sociacl_recovery_generation',
        'ck_sociacl_wrap_generation',
    }
    assert constraints['sociacl_keyring_state_pkey'] == 'PRIMARY KEY (principal)'
    assert '{43}' in constraints['ck_sociacl_keyring_principal']
    for name in ['ck_sociacl_keyring_floor', 'ck_sociacl_recovery_generation', 'ck_sociacl_wrap_generation']:
        assert '9007199254740991' in constraints[name] and '>= 0' in constraints[name]
    assert state['rls'] == [False, False]  # Global principal state, no tenant access.
    assert not state['policies'] and not state['triggers'] and not state['column_grants']
    assert all(grant[0] == 'OWNER' for grant in state['grants'])
    import copy
    expected = copy.deepcopy(before)
    for name, type_, collation in [
        ('lab_job_id', 'uuid', None), ('lab_device_id', 'uuid', None),
        ('lab_origin', 'character varying(32)', '"default"'),
        ('binding_sha256', 'character varying(64)', '"default"'),
        ('report_sha256', 'character varying(64)', '"default"'),
        ('measured_at', 'timestamp with time zone', None)]:
        expected['tables']['aiuditor_envelopes']['columns'].append(
            [name, type_, False, None, '', '', collation])
    reports = after['tables'].pop('aiuditor_envelope_reports')
    assert [(c[0], c[1], c[2]) for c in reports['columns']] == [
        ('tenant_id', 'uuid', True), ('origin', 'character varying(32)', True),
        ('job_id', 'uuid', True), ('payload_sha256', 'character varying(64)', True),
        ('accepted_envelope', 'jsonb', True), ('received_at', 'timestamp with time zone', True)]
    assert reports['rls'] == [True, True]
    assert len(reports['policies']) == 1
    assert 'app.current_tenant_id' in reports['policies'][0][4]
    assert 'app.current_tenant_id' in reports['policies'][0][5]
    assert any(c[1] == 'p' and 'tenant_id, origin, job_id' in c[2] for c in reports['constraints'])
    assert any(c[1] == 'f' and 'REFERENCES tenants(id)' in c[2] for c in reports['constraints'])
    expected['tables']['aiuditor_violations']['columns'].extend([
        ['enforcement_completed_at', 'timestamp with time zone', False, None, '', '', None],
        ['enforcement_attempts', 'integer', True, '0', '', '', None]])
    operations = after['tables'].pop('hypermesh_violation_operations')
    assert [(c[0], c[1], c[2]) for c in operations['columns']] == [
        ('tenant_id', 'uuid', True), ('operation_id', 'uuid', True),
        ('lease_id', 'uuid', True), ('binding', 'text', True),
        ('completed_at', 'timestamp with time zone', False)]
    assert operations['rls'] == [True, True]
    assert len(operations['policies']) == 1
    assert 'app.current_tenant_id' in operations['policies'][0][4]
    assert 'app.current_tenant_id' in operations['policies'][0][5]
    assert any(c[1] == 'p' and 'tenant_id, operation_id' in c[2] for c in operations['constraints'])
    assert any(c[1] == 'f' and 'REFERENCES tenants(id)' in c[2] for c in operations['constraints'])
    health = expected['tables']['hypermesh_device_health']
    health['columns'].extend([
        ['model_cache_hashes', 'jsonb', False, None, '', '', None],
        ['model_cache_available_bytes', 'bigint', False, None, '', '', None],
    ])
    health['constraints'].append(['ck_hypermesh_health_cache_available', 'c',
        'CHECK (model_cache_available_bytes IS NULL OR model_cache_available_bytes >= 0)', True])
    health['constraints'].sort(key=lambda row: row[0])
    jobs = expected['tables']['hypermesh_jobs']
    jobs['indexes'].append(['ix_hm_jobs_pending_device', "CREATE INDEX ix_hm_jobs_pending_device ON public.hypermesh_jobs USING btree (tenant_id, device_id, created_at, id) WHERE ((status)::text = 'pending'::text)"])
    jobs['indexes'].sort(key=lambda row: row[0])
    for column in jobs['columns']:
        if column[0] == 'source_ref':
            column[1] = 'character varying(1024)'
    jobs['columns'].extend([
        ['file_hash', 'character varying(256)', False, None, '', '', '"default"'],
        ['size_bytes', 'bigint', False, None, '', '', None],
    ])
    expected['tables']['hypermesh_host_registrations']['columns'].append(
        ['machine_identity', 'jsonb', False, None, '', '', None])
    expected['tables']['aiuditor_connections']['columns'].append(
        ['control_plane_id', 'character varying(128)', True, "'local'::character varying", '', '', '"default"'])
    identity = after['tables'].pop('aiuditor_machine_identities')
    assert identity['rls'] == [True, True]
    assert [(c[0], c[1], c[2]) for c in identity['columns']] == [
        ('authority_id', 'character varying(128)', True),
        ('tenant_id', 'uuid', True),
        ('control_plane_id', 'character varying(128)', True),
        ('device_id', 'uuid', True),
        ('request_id', 'uuid', True),
        ('state', 'jsonb', True),
        ('revoked', 'boolean', True),
    ]
    assert any(c[1] == 'p' and c[2] == 'PRIMARY KEY (authority_id, tenant_id, control_plane_id, device_id)' for c in identity['constraints'])
    assert len(identity['policies']) == 1
    assert 'app.current_tenant_id' in identity['policies'][0][4]
    assert 'app.current_tenant_id' in identity['policies'][0][5]
    crawl = after['tables'].pop('aiuditor_crawl_state')
    assert crawl['rls'] == [True, True]
    assert [(c[0], c[1], c[2]) for c in crawl['columns']] == [
        ('tenant_id', 'uuid', True), ('run_id', 'uuid', True),
        ('started_at', 'timestamp with time zone', True),
        ('finished_at', 'timestamp with time zone', False), ('error_count', 'integer', True),
    ]
    assert any(c[1] == 'p' and c[2] == 'PRIMARY KEY (tenant_id)' for c in crawl['constraints'])
    assert any(c[1] == 'f' and 'REFERENCES tenants(id)' in c[2] for c in crawl['constraints'])
    assert any(c[1] == 'c' and 'error_count >= 0' in c[2] for c in crawl['constraints'])
    assert len(crawl['policies']) == 1
    assert 'app.current_tenant_id' in crawl['policies'][0][4]
    assert 'app.current_tenant_id' in crawl['policies'][0][5]
    scoped = after['tables'].pop('aiuditor_private_model_admissions')
    assert scoped['rls'] == [True, True]
    assert {c[0] for c in scoped['columns']} == {
        'id', 'tenant_id', 'owner_sub', 'target', 'target_sha256', 'lab_job_id',
        'lab_device_id', 'status', 'evidence', 'audit', 'created_at',
    }
    assert len(scoped['policies']) == 1
    assert 'app.current_tenant_id' in scoped['policies'][0][4]
    assert 'app.current_tenant_id' in scoped['policies'][0][5]
    validations = after['tables'].pop('hypermesh_model_validations')
    assert validations['rls'] == [True, True]
    index = dict(validations['indexes'])['ix_hm_validation_planned_device']
    assert '(tenant_id, lab_device_id, created_at, expires_at)' in index
    assert "'planned'::text" in index
    assert {c[0] for c in validations['columns']} == {
        'id', 'tenant_id', 'owner_sub', 'revision_id', 'request_id', 'profile_id',
        'target', 'target_sha256', 'lab_job_id', 'lab_device_id', 'state',
        'evidence', 'created_at', 'expires_at',
    }
    assert len(validations['policies']) == 1
    assert 'app.current_tenant_id' in validations['policies'][0][4]
    assert 'app.current_tenant_id' in validations['policies'][0][5]
    budget = after['tables'].pop('hypermesh_model_account_budgets')
    assert {c[0] for c in budget['columns']} == {'account', 'reserved_entries'}
    assert any(c[1] == 'p' and c[2] == 'PRIMARY KEY (account)' for c in budget['constraints'])
    assert not budget['policies']  # global operational count contains no tenant data
    storage_health = after['tables'].pop('hypermesh_model_storage_health')
    assert storage_health['rls'] == [True, True]
    assert {c[0] for c in storage_health['columns']} == {'tenant_id', 'account', 'observed_at', 'physical_bytes', 'version_count', 'queue_age_seconds', 'janitor_at', 'healthy'}
    assert len(storage_health['policies']) == 1
    callbacks = after['tables'].pop('hypermesh_payment_callback_claims')
    assert callbacks['rls'] == [True, True]
    assert {c[0] for c in callbacks['columns']} == {'tenant_id', 'billing_record_id', 'token', 'expires_at'}
    assert len(callbacks['policies']) == 1
    assert 'app.current_tenant_id' in callbacks['policies'][0][4]
    assert 'app.current_tenant_id' in callbacks['policies'][0][5]
    assert any(c[1] == 'p' and c[2] == 'PRIMARY KEY (tenant_id, billing_record_id)' for c in callbacks['constraints'])
    claims = after['tables'].pop('hypermesh_model_poll_claims')
    assert claims['rls'] == [True, True]
    assert {c[0] for c in claims['columns']} == {'tenant_id', 'device_id', 'token', 'expires_at'}
    assert len(claims['policies']) == 1
    assert 'app.current_tenant_id' in claims['policies'][0][4]
    assert 'app.current_tenant_id' in claims['policies'][0][5]
    assert any(c[1] == 'p' and c[2] == 'PRIMARY KEY (tenant_id, device_id)' for c in claims['constraints'])
    closures = after['tables'].pop('hypermesh_model_owner_closures')
    assert closures['rls'] == [True, True]
    assert {c[0] for c in closures['columns']} == {'tenant_id', 'owner_sub', 'closed_at', 'recorded_at', 'reason'}
    assert len(closures['policies']) == 1
    assert 'app.current_tenant_id' in closures['policies'][0][4]
    assert 'app.current_tenant_id' in closures['policies'][0][5]
    erasures = after['tables'].pop('hypermesh_model_owner_erasures')
    assert erasures['rls'] == [True, True]
    assert {c[0] for c in erasures['columns']} == {
        'tenant_id', 'owner_sub', 'closed_at', 'completed_at',
        'revisions', 'validations', 'lease_targets',
    }
    assert len(erasures['policies']) == 1
    assert 'app.current_tenant_id' in erasures['policies'][0][4]
    assert 'app.current_tenant_id' in erasures['policies'][0][5]
    assert any(c[1] == 'p' and c[2] == 'PRIMARY KEY (tenant_id, owner_sub)' for c in erasures['constraints'])
    assert any(c[1] == 'f' and 'REFERENCES tenants(id) ON DELETE CASCADE' in c[2] for c in erasures['constraints'])
    assert any(c[0] == 'ck_hm_owner_erasure_counts' for c in erasures['constraints'])
    revisions = after['tables'].pop('hypermesh_model_revisions')
    assert revisions['rls'] == [True, True]
    assert {c[0] for c in revisions['columns']} == {
        'id', 'tenant_id', 'owner_sub', 'request_id', 'name', 'license', 'size_bytes',
        'state', 'manifest', 'storage_account', 'storage_container', 'sealed_files',
        'expires_at', 'created_at', 'sealed_at', 'scan_evidence', 'scan_state',
        'inspection', 'inspection_claim_id', 'inspection_claim_until', 'inspection_failures',
        'revoked_at', 'delete_requested_at', 'retain_until', 'retention_hold', 'lifecycle_audit', 'cleanup_claim_until',
        'inactivity_anchor_at', 'inactivity_notice_at', 'inactivity_delete_after',
    }
    guard = after['functions'].pop('hm_guard_model_revision_delete()')
    assert "OLD.state <> 'deleted'" in guard['definition']
    assert 'RAISE EXCEPTION' in guard['definition']
    assert [(t[0], 'BEFORE DELETE ON public.hypermesh_model_revisions' in t[1]) for t in revisions['triggers']] == [
        ('hm_model_revision_delete_guard', True),
    ]
    revisions['triggers'] = []
    assert len(revisions['policies']) == 1
    assert 'app.current_tenant_id' in revisions['policies'][0][4]
    assert 'app.current_tenant_id' in revisions['policies'][0][5]
    sites = after['tables'].pop('hypermesh_sites')
    assert sites['rls'] == [True, True]
    assert [(c[0], c[1], c[2]) for c in sites['columns']] == [
        ('tenant_id', 'uuid', True),
        ('site_id', 'character varying(128)', True),
        ('owner_org', 'uuid', False),
        ('created_at', 'timestamp with time zone', True),
    ]
    assert any(c[1] == 'p' and c[2] == 'PRIMARY KEY (tenant_id, site_id)' for c in sites['constraints'])
    assert len(sites['policies']) == 4
    flags = after['tables'].pop('hypermesh_safety_flags')
    assert flags['rls'] == [True, True]
    assert [(c[0], c[1], c[2]) for c in flags['columns']][:4] == [
        ('id', 'uuid', True),
        ('tenant_id', 'uuid', True),
        ('gateway_id', 'uuid', True),
        ('lease_id', 'uuid', True),
    ]
    assert len(flags['policies']) == 6
    assert any('app.safety_flag_retention' in str(policy) for policy in flags['policies'])
    tokens = expected['tables']['hypermesh_site_tokens']
    tokens['policies'].append([
        'site_token_lookup_by_hash', 'r', True, ['PUBLIC'],
        "((secret_hash)::text = NULLIF(current_setting('app.site_token_hash'::text, true), ''::text))",
        None,
    ])
    tokens['policies'].sort(key=lambda row: row[0])
    expected['tables']['hypermesh_leases']['columns'].extend([
        ['payment_amount_atoms', 'bigint', False, None, '', '', None],
        ['payment_test_credit_available', 'boolean', True, 'false', '', '', None],
        ['close_requested_at', 'timestamp with time zone', False, None, '', '', None],
        ['private_model', 'jsonb', False, None, '', '', None],
        ['offer_request_sha256', 'character varying(64)', False, None, '', '', '"default"'],
    ])
    # Explicitly validate the additive protection registry before comparing the
    # remaining schema with the frozen baseline. Neither baseline is rewritten.
    expected['tables']['hypermesh_leases']['columns'].extend([
        ['protection_policy_version', 'integer', True, '1', '', '', None],
        ['protection_requirements', 'jsonb', True, "'[]'::jsonb", '', '', None],
        ['contract_until', 'timestamp with time zone', False, None, '', '', None],
        ['throughput_map_version', 'character varying(96)', False, None, '', '', '"default"'],
        ['processing_fee_policy', 'jsonb', False, None, '', '', None],
        ['processing_fee_binding', 'jsonb', False, None, '', '', None],
        ['payout_terms', 'jsonb', False, None, '', '', None],
        ['host_certified_at_start', 'boolean', False, None, '', '', None],
        ['self_use', 'boolean', True, 'false', '', '', None],
    ])
    members = after['tables'].pop('hypermesh_self_use_members')
    assert members['rls'] == [True, True]
    assert [(c[0], c[1], c[2]) for c in members['columns']] == [
        ('tenant_id', 'uuid', True), ('host_org_id', 'uuid', True),
        ('member_subject', 'uuid', True), ('granted_by', 'uuid', True),
        ('created_at', 'timestamp with time zone', True),
    ]
    assert len(members['policies']) == 1 and 'app.current_tenant_id' in str(members['policies'])
    self_use_guard = after['functions'].pop('hm_self_use_immutable()')
    assert 'Self-use cannot charge or extend' in self_use_guard['definition']
    self_use_trigger = next(t for t in after['tables']['hypermesh_leases']['triggers'] if t[0] == 'self_use_immutable')
    after['tables']['hypermesh_leases']['triggers'].remove(self_use_trigger)
    approvals = after['tables'].pop('hypermesh_protection_approvals')
    assert approvals['rls'] == [True, True]
    assert [(c[0], c[1], c[2]) for c in approvals['columns']] == [
        ('id', 'uuid', True), ('tenant_id', 'uuid', True),
        ('device_id', 'uuid', True), ('mode', 'character varying(32)', True),
        ('binding', 'jsonb', True), ('evidence_sha256', 'character varying(64)', True),
        ('reviewed_by', 'uuid', True), ('observed_at', 'timestamp with time zone', True),
        ('reviewed_at', 'timestamp with time zone', True), ('expires_at', 'timestamp with time zone', True),
        ('revoked_at', 'timestamp with time zone', False), ('revoked_by', 'uuid', False),
        ('revocation_reason', 'character varying(256)', False),
    ]
    assert len(approvals['policies']) == 4
    assert all('app.current_tenant_id' in str(policy) for policy in approvals['policies'])
    assert any(index[0] == 'ix_hm_protection_device' and '(tenant_id, device_id, expires_at)' in index[1] for index in approvals['indexes'])
    assert {c[0] for c in approvals['constraints'] if c[1] == 'c'} == {
        'ck_hm_protection_mode', 'ck_hm_protection_window',
        'ck_hm_protection_digest', 'ck_hm_protection_revocation',
    }
    protection_function = after['functions'].pop('hm_protection_immutable()')
    assert 'NEW.protection_requirements <> OLD.protection_requirements' in protection_function['definition']
    assert 'OLD.revoked_at IS NOT NULL' in protection_function['definition']
    assert len(approvals['triggers']) == 1
    assert approvals['triggers'][0][0] == 'protection_immutable'
    assert approvals['triggers'][0][2] == 'O'
    fee_guard = after['functions'].pop('hm_processing_fee_immutable()')
    assert "'capture'" in fee_guard['definition']
    fee_trigger = next(t for t in after['tables']['hypermesh_leases']['triggers'] if t[0] == 'processing_fee_immutable')
    assert 'BEFORE UPDATE ON public.hypermesh_leases' in fee_trigger[1]
    after['tables']['hypermesh_leases']['triggers'].remove(fee_trigger)
    payout_guard = after['functions'].pop('hm_payout_terms_immutable()')
    assert 'IS DISTINCT FROM' in payout_guard['definition']
    leases = after['tables']['hypermesh_leases']
    private_use_index = next(i for i in leases['indexes'] if i[0] == 'ix_hm_private_activation')
    assert 'validation_id' in private_use_index[1] and 'activated_at IS NOT NULL' in private_use_index[1]
    leases['indexes'].remove(private_use_index)
    payout_trigger = next(t for t in leases['triggers'] if t[0] == 'payout_terms_immutable')
    assert 'BEFORE UPDATE ON public.hypermesh_leases' in payout_trigger[1]
    leases['triggers'].remove(payout_trigger)
    receipt_guard = after['functions'].pop('hm_lease_certification_immutable()')
    assert 'OLD.activated_at IS NOT NULL' in receipt_guard['definition']
    assert 'NEW.host_certified_at_start IS DISTINCT FROM OLD.host_certified_at_start' in receipt_guard['definition']
    receipt_trigger = next(t for t in leases['triggers'] if t[0] == 'lease_certification_immutable')
    assert 'BEFORE UPDATE ON public.hypermesh_leases' in receipt_trigger[1]
    leases['triggers'].remove(receipt_trigger)
    protection_constraint = next(c for c in leases['constraints'] if c[0] == 'ck_hm_lease_protection')
    assert 'protection_policy_version = 1' in protection_constraint[2]
    assert 'physical_memory' in protection_constraint[2] and 'confidential_execution' in protection_constraint[2]
    leases['constraints'].remove(protection_constraint)
    protection_trigger = next(t for t in leases['triggers'] if t[0] == 'protection_immutable')
    assert 'BEFORE UPDATE ON public.hypermesh_leases' in protection_trigger[1]
    assert 'hm_protection_immutable()' in protection_trigger[1]
    assert protection_trigger[2] == 'O'
    leases['triggers'].remove(protection_trigger)
    pin_function = after['functions'].pop('hypermesh_private_lease_pin_immutable()')
    assert 'OLD.private_model IS NOT NULL' in pin_function['definition']
    assert 'NEW.private_model IS DISTINCT FROM OLD.private_model' in pin_function['definition']
    assert "NEW.private_model = OLD.private_model - 'target'" in pin_function['definition']
    assert "to_jsonb(NEW) - 'private_model' = to_jsonb(OLD) - 'private_model'" in pin_function['definition']
    assert "OLD.status IN ('offered','ended','failed','refunded')" in pin_function['definition']
    assert "r.state='deleted' AND NOT r.retention_hold" in pin_function['definition']
    assert "c.closed_at <= clock_timestamp() - interval '89 days'" in pin_function['definition']
    assert 'Exact version inventory has no live blobs' in pin_function['definition']
    assert 'FOR SHARE OF v,r,c' in pin_function['definition']
    assert 'record_created_at' in pin_function['definition']
    triggers = after['tables']['hypermesh_leases']['triggers']
    assert len(triggers) == 1
    assert triggers[0][0] == 'hypermesh_private_lease_pin_immutable'
    assert 'BEFORE UPDATE ON public.hypermesh_leases' in triggers[0][1]
    assert triggers[0][2] == 'O'
    after['tables']['hypermesh_leases']['triggers'] = []
    lease_indexes = expected['tables']['hypermesh_leases']['indexes']
    lease_indexes.append([
        'ix_hm_leases_tenant_live',
        "CREATE INDEX ix_hm_leases_tenant_live ON public.hypermesh_leases USING btree "
        "(tenant_id, status) WHERE ((status)::text = ANY ((ARRAY['starting'::character varying, "
        "'active'::character varying])::text[]))",
    ])
    lease_indexes.sort(key=lambda row: row[0])
    # Owner migration 0068: exact additive evidence columns on both adoption
    # paths. Retain the full comparison of existing types, RLS, grants and data.
    expected['tables']['hypermesh_devices']['columns'].extend([
        ['environment_changed_at', 'timestamp with time zone', False, None, '', '', None],
        ['observed_environment_hash', 'character varying(71)', False, None, '', '', '"default"'],
        ['certified_environment_hash', 'character varying(71)', False, None, '', '', '"default"'],
    ])
    expected['tables']['hypermesh_jobs']['columns'].extend([
        ['result_effects_completed_at', 'timestamp with time zone', False, None, '', '', None],
        ['environment_hash', 'character varying(71)', False, None, '', '', '"default"'],
        # The reconciled owner graph runs lab binding before certification.
        ['lab_binding', 'jsonb', False, None, '', '', None],
        ['certification_evidence', 'jsonb', False, None, '', '', None],
    ])
    expected['tables']['hypermesh_scorecards']['columns'].extend([
        ['certification_job_id', 'uuid', False, None, '', '', None],
        ['environment_hash', 'character varying(71)', False, None, '', '', '"default"'],
    ])
    assert_source_subscription_delta(expected, after)
    # Owner platform history also merges the reviewed share-lookup hardening.
    # Validate its full body and exact execution grants, then retain the full
    # comparison for every other schema object and field.
    signature = 'sociacl_share_lookup_by_hash(p_hash character varying)'
    lookup = after['functions'][signature]
    assert ' '.join(lookup['definition'].split()) == (
        "CREATE OR REPLACE FUNCTION public.sociacl_share_lookup_by_hash(p_hash character varying) "
        "RETURNS SETOF sociacl_share_links LANGUAGE sql STABLE SECURITY DEFINER "
        "SET search_path TO 'pg_catalog', 'public', 'pg_temp' AS $function$ "
        "SELECT * FROM public.sociacl_share_links WHERE token_hash OPERATOR(pg_catalog.=) "
        "p_hash LIMIT 1 $function$"
    )
    grants = [['OWNER', 'EXECUTE', False], ['controlplane', 'EXECUTE', False],
              ['controlplane_app', 'EXECUTE', False]]
    assert lookup['grants'] == grants
    expected['functions'][signature] = {'definition': lookup['definition'], 'grants': grants}
    assert_contact_lane_delta(after)
    assert_same_schema(after, expected)


def assert_source_subscription_delta(before, after):
    subscriptions = after['tables']['controlplane_event_subscriptions']
    added = [column for column in subscriptions['columns'] if column[0] == 'source_service']
    assert len(added) == 1 and added[0][1:4] == ['text', False, None]
    subscriptions['columns'].remove(added[0])
    indexes = after['tables']['controlplane_events']['indexes']
    added = [index for index in indexes if index[0] == 'ix_controlplane_events_type_source_id']
    assert len(added) == 1
    assert "event_type, ((envelope ->> 'service'::text)), id" in added[0][1]
    indexes.remove(added[0])
    signature = ('register_controlplane_event_consumer(p_group text, p_event_types text[], '
                 'p_mode text, p_max_attempts integer, p_source_service text)')
    source_registration = after['functions'].pop(signature)
    definition = source_registration['definition']
    assert 'SECURITY DEFINER' in definition and "'pg_catalog', 'public', 'pg_temp'" in definition
    assert "e.envelope->>'service' = p_source_service" in definition
    assert 'source filter cannot change' in definition
    assert source_registration['grants'] == before['functions'][signature.replace(', p_source_service text', '')]['grants']
    for signature in (
        signature.replace(', p_source_service text', ''), 'deliver_controlplane_event()',
        'replay_controlplane_event_deliveries(p_group text, p_after_event_id bigint)',
    ):
        changed = after['functions'][signature]
        assert changed['grants'] == before['functions'][signature]['grants']
        if signature == 'deliver_controlplane_event()':
            assert "s.source_service = NEW.envelope->>'service'" in changed['definition']
        elif signature.startswith('replay_controlplane_event_deliveries'):
            assert changed['definition'].count("s.source_service = e.envelope->>'service'") == 2
        else:
            assert 'SELECT s.source_service INTO v_source' in changed['definition']
        after['functions'][signature] = before['functions'][signature]


def test_payout_subject_forward_migration_preserves_receipt_and_refuses_lossy_downgrade():
    from sqlalchemy.exc import IntegrityError

    with isolated_postgres() as url:
        migrations.upgrade(url, baseline_only=True)
        engine = create_engine(url)
        tenant, org = uuid.uuid4(), uuid.uuid4()
        try:
            with engine.begin() as connection:
                command.upgrade(
                    migrations._config(CHAINS, "payment_service", connection),
                    "payment_service_0054_payout_addr",
                )
                connection.execute(
                    text(
                        "INSERT INTO tenants (id, name, is_active) VALUES (:id, 'subject-migration', true)"
                    ),
                    {"id": tenant},
                )
                connection.execute(
                    text("""INSERT INTO host_payout_addresses
                    (tenant_id, host_org_id, chain_id, address, verified_by_sub,
                     proof_audience, proof_message_hash, proof_signature_hash, verified_at)
                    VALUES (:tenant, :org, 84532, :address, :subject, 'test', :hash, :hash, now())"""),
                    {
                        "tenant": tenant,
                        "org": org,
                        "address": "0x" + "a" * 40,
                        "subject": "h" * 256,
                        "hash": "b" * 64,
                    },
                )
            # Isolate the subject-width regression from later irreversible
            # financial-clock migrations, which deliberately block earlier.
            with engine.begin() as connection:
                command.upgrade(migrations._config(CHAINS, "payment_service", connection),
                                "payment_service_0055_subject")
            with engine.begin() as connection:
                assert (
                    connection.execute(
                        text("SELECT verified_by_sub FROM host_payout_addresses")
                    ).scalar_one()
                    == "h" * 256
                )
                connection.execute(
                    text("UPDATE host_payout_addresses SET verified_by_sub=:subject"),
                    {"subject": "h" * 512},
                )
            with pytest.raises(IntegrityError), engine.begin() as connection:
                command.downgrade(
                    migrations._config(CHAINS, "payment_service", connection),
                    "payment_service_0054_payout_addr",
                )
            assert (
                migrations.current_heads(url)["payment_service"]
                == "payment_service_0055_subject"
            )
            with engine.connect() as connection:
                assert (
                    connection.execute(
                        text("SELECT verified_by_sub FROM host_payout_addresses")
                    ).scalar_one()
                    == "h" * 512
                )
        finally:
            engine.dispose()


def assert_subject_scope_delta(before, after):
    old = dict(before["tables"]["users"]["indexes"])
    new = dict(after["tables"]["users"]["indexes"])
    assert old.pop("ix_users_keycloak_sub_unique") == (
        "CREATE UNIQUE INDEX ix_users_keycloak_sub_unique ON public.users "
        "USING btree (keycloak_sub) WHERE (keycloak_sub IS NOT NULL)"
    )
    assert new.pop("uq_users_platform_keycloak_sub") == (
        "CREATE UNIQUE INDEX uq_users_platform_keycloak_sub ON public.users "
        "USING btree (keycloak_sub) WHERE ((tenant_id IS NULL) AND (keycloak_sub IS NOT NULL))"
    )
    assert new.pop("uq_users_tenant_keycloak_sub") == (
        "CREATE UNIQUE INDEX uq_users_tenant_keycloak_sub ON public.users "
        "USING btree (tenant_id, keycloak_sub) WHERE ((tenant_id IS NOT NULL) AND (keycloak_sub IS NOT NULL))"
    )
    assert old == new
    # Other schema fields still compare exactly in the existing delta check.
    after["tables"]["users"]["indexes"] = before["tables"]["users"]["indexes"]


def assert_payment_financial_schema_delta(after):
    assert_test_retention_schema_delta(after)
    postal = after['tables'].pop('connect_payout_locations')
    assert postal['policies'], "Postal evidence must remain tenant isolated"
    clock_tables = {'host_payout_addresses', 'connect_recipient_accounts', 'billing_tax_orders',
        'billing_tax_calculations', 'connect_bank_approvals',
        'connect_reversal_exposure_observations', 'connect_control_proofs', 'payer_mismatch_accounts'}
    source_tables = clock_tables | {'connect_access_states', 'connect_access_grants',
        'connect_access_results', 'payer_mismatch_accounts'}
    admission_tables = {'connect_recipient_accounts', 'host_payout_addresses',
        'connect_access_grants', 'connect_control_proofs', 'connect_bank_approvals'}
    for name in source_tables:
        table = after['tables'][name]
        trigger = next(t for t in table['triggers'] if t[0] == 'account_financial_epoch')
        assert 'AFTER INSERT OR DELETE OR UPDATE' in trigger[1]
        assert 'payment_account_financial_epoch()' in trigger[1] and trigger[2] == 'O'
        table['triggers'].remove(trigger)
        truncate_trigger = next(t for t in table['triggers'] if t[0]=='account_financial_not_truncated')
        assert 'BEFORE TRUNCATE' in truncate_trigger[1] and 'account_refuse_financial_truncate()' in truncate_trigger[1]
        table['triggers'].remove(truncate_trigger)
        if name in admission_tables:
            trigger = next(t for t in table['triggers'] if t[0] == 'account_new_authority')
            assert 'BEFORE INSERT' in trigger[1]
            assert 'payment_account_new_authority()' in trigger[1] and trigger[2] == 'O'
            table['triggers'].remove(trigger)
        if name in clock_tables:
            cols = [c for c in table['columns'] if c[0] in {'financial_activity_at','financial_retain_until'}]
            assert [(c[0],c[1],c[2]) for c in cols] == [
                ('financial_activity_at','timestamp with time zone',False),
                ('financial_retain_until','timestamp with time zone',False)]
            table['columns'] = [c for c in table['columns'] if c not in cols]
            constraint = next(c for c in table['constraints'] if c[0] == 'ck_'+name+'_financial_clock')
            table['constraints'].remove(constraint)
            index = next(i for i in table['indexes'] if i[0] == 'ix_'+name+'_financial_due')
            table['indexes'].remove(index)
            trigger = next(t for t in table['triggers'] if t[0] == 'account_financial_clock')
            assert 'BEFORE INSERT OR UPDATE' in trigger[1]
            assert 'payment_financial_clock()' in trigger[1] and trigger[2] == 'O'
            table['triggers'].remove(trigger)
    risk = after['tables']['payer_mismatch_accounts']['triggers']
    expiry = next(t for t in risk if t[0] == 'account_payer_risk_expiry')
    assert 'BEFORE DELETE' in expiry[1] and 'payment_payer_risk_expiry_guard()' in expiry[1]
    risk.remove(expiry)
    recipient = after['tables']['connect_recipient_accounts']
    initiator = next(c for c in recipient['columns'] if c[0]=='initiated_by_sub')
    assert initiator[1:4] == ['character varying(512)',False,None]
    recipient['columns'].remove(initiator)
    constraint = next(c for c in recipient['constraints'] if c[0]=='ck_recipient_initiator')
    recipient['constraints'].remove(constraint)
    for signature in ('payment_account_financial_state(p_subject text, p_closed_at timestamp with time zone)',
                      'payment_payer_risk_expiry_guard()',
                      'payment_erase_expired_payer_risk(p_subject text, p_closed_at timestamp with time zone, p_limit integer)',
                      'payment_access_actor_redaction()', 'payment_access_actor_unlink()',
                      'payment_access_owner_admission()',
                      'payment_erase_personal_access(p_subject text, p_closed_at timestamp with time zone, p_tenant uuid, p_limit integer)',
                      'payment_financial_clock()', 'payment_account_financial_epoch()', 'payment_account_new_authority()',
                      'payment_financial_inventory_parties(p_table text, p_source jsonb)',
                      'payment_prime_financial_sources(p_subject text, p_closed_at timestamp with time zone, p_tenant uuid, p_limit integer)'):
        function = after['functions'].pop(signature)
        assert 'SECURITY DEFINER' in function['definition']
        assert "search_path TO 'pg_catalog'" in function['definition']
        assert function['grants'] == [['OWNER','EXECUTE',False]]


def assert_journal_schema_delta(after):
    exposure = after["tables"].pop("connect_reversal_exposure_observations")
    assert exposure["rls"] == [True, True]
    assert {policy[0] for policy in exposure["policies"]} == {"reversal_exposure_select", "reversal_exposure_insert"}
    assert {trigger[0] for trigger in exposure["triggers"]} == {"reversal_exposure_update", "reversal_exposure_delete", "reversal_exposure_truncate"}
    assert_control_proof_schema_delta(after)
    bank = after["tables"].pop("connect_bank_approvals")
    assert bank["rls"] == [True, True]
    assert {policy[0] for policy in bank["policies"]} == {"bank_approval_select", "bank_approval_insert"}
    assert all("app.current_tenant_id" in str(policy) for policy in bank["policies"])
    assert {trigger[0] for trigger in bank["triggers"]} == {
        "connect_bank_approvals_update", "connect_bank_approvals_delete", "connect_bank_approvals_truncate",
    }
    assert {column[0] for column in bank["columns"]} == {
        "id", "tenant_id", "host_org_id", "enrollment_attempt_id", "account_id", "platform_id",
        "bank_id", "owner_sub", "member_id", "epoch", "policy_hashes", "bank_observation",
        "second_factor_at", "approved_at",
    }
    ended = after["tables"].pop("connect_ended_sessions")
    assert ended["rls"] == [True, True]
    assert {column[0] for column in ended["columns"]} == {"session_key", "ended_at"}
    assert {p[0] for p in ended["policies"]} == {"ended_session_select", "ended_session_insert", "ended_session_cleanup"}
    assert {t[0] for t in ended["triggers"]} == {"connect_ended_sessions_update", "connect_ended_sessions_truncate"}
    for table in ("connect_access_states", "connect_access_grants", "connect_access_results"):
        access = after["tables"].pop(table)
        assert access["rls"] == [True, True]
        assert all("app.current_tenant_id" in str(policy) for policy in access["policies"])
        if table == "connect_access_grants":
            unlink = next(t for t in access['triggers'] if t[0] == 'zz_access_actor_unlink')
            assert 'AFTER UPDATE' in unlink[1] and 'payment_access_actor_unlink()' in unlink[1]
            access['triggers'].remove(unlink)
            update = next(t for t in access['triggers'] if t[0] == 'connect_access_grants_update')
            assert 'payment_access_actor_redaction()' in update[1]
        elif table == "connect_access_states":
            admission = next(t for t in access['triggers'] if t[0] == 'account_access_owner_admission')
            assert 'BEFORE INSERT OR UPDATE' in admission[1] and 'payment_access_owner_admission()' in admission[1]
            access['triggers'].remove(admission)
        assert {trigger[0] for trigger in access["triggers"]} == ({table + "_delete", table + "_truncate"} | ({table + "_update"} if table != "connect_access_states" else {"connect_access_epoch"}))
        assert "client_secret" not in {column[0] for column in access["columns"]}
    for function in ("connect_access_legacy()", "connect_access_epoch()"):
        assert after["functions"].pop(function)
    assert "usdc_deposit_addresses_hd_index_seq" not in after["sequences"]
    for table in ("connect_recipient_accounts", "payer_mismatch_accounts", "billing_tax_orders", "billing_tax_calculations"):
        assert after["tables"].pop(table)["rls"] == [True, True]
    for function in ("connect_recipient_progress_only()", "connect_recipient_immutable()", "tax_history_retained()", "tax_order_binding()", "tax_calculation_progress()"):
        assert after["functions"].pop(function)


def assert_control_proof_schema_delta(after):
    proofs = after["tables"].pop("connect_control_proofs")
    assert proofs["rls"] == [True, True]
    assert [(c[0], c[1], c[2]) for c in proofs["columns"]] == [
        ("id", "uuid", True), ("tenant_id", "uuid", True),
        ("host_org_id", "uuid", True), ("enrollment_attempt_id", "uuid", True),
        ("account_id", "character varying(255)", True),
        ("bank_id", "character varying(255)", True),
        ("owner_sub", "character varying(512)", True),
        ("challenge_nonce", "character varying(64)", True),
        ("ownership_snapshot", "jsonb", True),
        ("created_at", "timestamp with time zone", True),
        ("expires_at", "timestamp with time zone", True),
        ("report", "jsonb", False),
        ("accepted_at", "timestamp with time zone", False),
    ]
    constraints = {row[0]: row[2] for row in proofs["constraints"]}
    assert set(constraints) == {
        "connect_control_proofs_pkey", "connect_control_proofs_tenant_id_fkey",
        "uq_control_nonce", "ck_control_nonce", "ck_control_owner",
        "ck_control_account", "ck_control_bank", "ck_control_lifetime", "ck_control_accepted",
    }
    assert constraints["uq_control_nonce"] == "UNIQUE (challenge_nonce)"
    assert "REFERENCES tenants(id) ON DELETE RESTRICT" in constraints["connect_control_proofs_tenant_id_fkey"]
    assert "accepted_at IS NOT NULL" in constraints["ck_control_accepted"]
    assert "expires_at > created_at" in constraints["ck_control_lifetime"]
    assert len(proofs["policies"]) == 4
    assert {p[0] for p in proofs["policies"]} == {
        "control_proof_select", "control_proof_insert", "control_proof_update", "control_proof_delete",
    }
    assert all("app.current_tenant_id" in str(p) for p in proofs["policies"])
    assert {t[0] for t in proofs["triggers"]} == {
        "control_proof_update", "control_proof_delete", "control_proof_truncate",
    }
    for name, definition, enabled in proofs["triggers"]:
        assert enabled == "O"
        if name == "control_proof_update":
            assert "BEFORE UPDATE" in definition and "control_proof_once()" in definition
        else:
            assert "connect_recipient_immutable()" in definition
            assert ("BEFORE DELETE" if name == "control_proof_delete" else "BEFORE TRUNCATE") in definition
    guard = after["functions"].pop("control_proof_once()")
    assert "OLD.report IS NOT NULL OR NEW.report IS NULL OR NEW.accepted_at IS NULL" in guard["definition"]
    assert "IS DISTINCT FROM" in guard["definition"]
    assert "RAISE EXCEPTION" in guard["definition"]


@pytest.mark.parametrize("tenant_context", [None, "another_tenant"])
def test_closure_downgrade_cannot_hide_requests_under_forced_rls(tenant_context):
    with isolated_postgres() as url:
        migrations.upgrade(url, chains=["platform"], baseline_only=True)
        engine = create_engine(url)
        tenant = uuid.uuid4()
        # Isolate the 0058 downgrade regression. Later irreversible retirement
        # revisions intentionally refuse to downgrade before reaching it.
        with engine.begin() as cx:
            config = Config()
            config.set_main_option("script_location", str(CHAINS))
            config.set_main_option("version_locations", str(CHAINS / "platform/versions"))
            config.attributes.update(connection=cx, version_table="alembic_version_platform")
            command.upgrade(config, "platform_0058_closure_requests")
        try:
            with engine.begin() as cx:
                cx.execute(text("INSERT INTO tenants (id, name, is_active) VALUES (:t, 'closure-test', true)"), {"t": tenant})
                cx.execute(text("INSERT INTO account_closure_requests VALUES (:t, 'subject', now(), 'subject', 'self_service')"), {"t": tenant})
                cx.execute(text("CREATE ROLE closure_migrator NOSUPERUSER NOBYPASSRLS"))
                cx.execute(text("GRANT USAGE ON SCHEMA public TO closure_migrator"))
                cx.execute(text("ALTER TABLE account_closure_requests OWNER TO closure_migrator"))
                cx.execute(text("GRANT SELECT, UPDATE ON alembic_version_platform TO closure_migrator"))
            with pytest.raises(Exception, match="row-level security"):
                with engine.begin() as cx:
                    cx.execute(text("SET LOCAL ROLE closure_migrator"))
                    if tenant_context:
                        cx.execute(text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(uuid.uuid4())})
                    # Prove the original query cannot see this tenant's record.
                    assert cx.execute(text("SELECT count(*) FROM account_closure_requests")).scalar_one() == 0
                    config = Config()
                    config.set_main_option("script_location", str(CHAINS))
                    config.set_main_option("version_locations", str(CHAINS / "platform/versions"))
                    config.attributes.update(connection=cx, version_table="alembic_version_platform")
                    command.downgrade(config, "platform_0057_checkpoint_replay")
            assert migrations.current_heads(url)["platform"] == "platform_0058_closure_requests"
            with engine.connect() as cx:
                assert cx.execute(text("SELECT count(*) FROM account_closure_requests")).scalar_one() == 1
        finally:
            engine.dispose()


@pytest.mark.parametrize('record_kind', ['identity', 'keys'])
def test_retirement_downgrade_preserves_recorded_tombstones(record_kind):
    with isolated_postgres() as url:
        migrations.upgrade(url, chains=['platform'], baseline_only=True)
        engine = create_engine(url)
        try:
            with engine.begin() as cx:
                config = Config()
                config.set_main_option('script_location', str(CHAINS))
                config.set_main_option('version_locations', str(CHAINS / 'platform/versions'))
                config.attributes.update(connection=cx, version_table='alembic_version_platform')
                command.upgrade(config, 'platform_0059_account_lifecycles')
            with engine.begin() as cx:
                if record_kind == 'identity':
                    cx.execute(text("INSERT INTO identity_retirements VALUES ('retired-person', now())"))
                else:
                    tenant = uuid.uuid4()
                    cx.execute(text("INSERT INTO tenants (id,name,is_active) VALUES (:t,'retirement',true)"), {'t':tenant})
                    cx.execute(text("INSERT INTO api_key_owner_closures VALUES (:t,'retired-person',now())"), {'t':tenant})
            with pytest.raises(RuntimeError, match='tombstones cannot be discarded'):
                with engine.begin() as cx:
                    config = Config()
                    config.set_main_option('script_location', str(CHAINS))
                    config.set_main_option('version_locations', str(CHAINS / 'platform/versions'))
                    config.attributes.update(connection=cx, version_table='alembic_version_platform')
                    command.downgrade(config, 'platform_0058_closure_requests')
            assert migrations.current_heads(url)['platform'] == 'platform_0059_account_lifecycles'
        finally:
            engine.dispose()


def assert_test_retention_schema_delta(after):
    billing = after['tables']['billing_records']
    mode = [c for c in billing['columns'] if c[0]=='stripe_livemode']
    assert mode == [['stripe_livemode','boolean',False,None,'','',None]]
    billing['columns'] = [c for c in billing['columns'] if c not in mode]
    triggers = [t for t in billing['triggers'] if t[0]=='billing_stripe_mode_immutable']
    assert len(triggers)==1 and triggers[0][2]=='O'
    assert 'BEFORE INSERT OR UPDATE ON public.billing_records' in triggers[0][1]
    billing['triggers'] = [t for t in billing['triggers'] if t not in triggers]
    expected = {
        "account_test_data_policy": {
            "singleton",
            "database_oid",
            "database_name",
            "enabled",
            "cluster_identifier",
        },
        "account_test_delete_capabilities": {
            "transaction_id",
            "relation",
            "row_digest",
            "source_subject",
            "source_closed_at",
            "row_tid",
        },
        "account_test_policy_originals": {"signature", "definition"},
        "account_test_delete_guard_originals": {"signature", "definition"},
    }
    for name, columns in expected.items():
        table = after["tables"].pop(name)
        assert {c[0] for c in table["columns"]} == columns
        assert table["rls"] == [True, True]
        assert not table["policies"] and not table["column_grants"]
        assert all(grant[0] == "OWNER" for grant in table["grants"])
        if name == "account_test_delete_capabilities":
            assert len(table["triggers"]) == 1
            trigger = table["triggers"][0]
            assert (
                trigger[0] == "test_delete_capabilities_ephemeral" and trigger[2] == "O"
            )
            assert "DEFERRABLE INITIALLY DEFERRED" in trigger[1]
        else:
            assert not table["triggers"]
    for signature in (
        "account_test_data_enabled()",
        "account_lock_test_data_policy()",
        "account_test_row_delete_allowed(p_relation oid, p_row jsonb)",
        "account_test_capabilities_ephemeral()",
    ):
        function = after["functions"].pop(signature)
        assert "SECURITY DEFINER" in function["definition"]
        assert "search_path TO 'pg_catalog'" in function["definition"]
        assert "row_security TO 'off'" in function["definition"]
        assert function["grants"] == [["OWNER", "EXECUTE", False]]
    authority_names = {
        "account_test_stripe_metadata",
        "account_billing_stripe_mode_immutable",
        "account_test_table_name",
        "account_lock_test_financial_sources",
        "account_test_read_row",
        "account_test_scope",
        "account_test_check_row",
        "account_test_check_row_pre0083",
        "account_test_check_parties",
        "account_test_edge",
        "account_stage_test_delete",
        "account_delete_test_financial_row",
        "account_clear_test_delete_capabilities",
        "account_test_json_mentions",
        "account_reconcile_test_financial_bindings",
    }
    authority = {
        key: value
        for key, value in after["functions"].items()
        if key.split("(")[0] in authority_names
    }
    assert {key.split("(")[0] for key in authority} == authority_names
    assert len(authority) == len(authority_names)
    for signature, function in authority.items():
        assert "SECURITY DEFINER" in function["definition"]
        assert "search_path TO 'pg_catalog', 'pg_temp'" in function["definition"]
        assert "row_security TO 'off'" in function["definition"]
        assert function["grants"] == [["OWNER", "EXECUTE", False]]
        after["functions"].pop(signature)
    for signature in (
        "connect_recipient_immutable()",
        "payment_payer_risk_expiry_guard()",
        "tax_history_retained()",
    ):
        definition = after["functions"][signature]["definition"]
        assert (
            definition.count(
                "public.account_test_row_delete_allowed(TG_RELID,to_jsonb(OLD))"
            )
            == 1
        )
        assert "TG_LEVEL='ROW' AND TG_OP='DELETE'" in definition


def assert_hypermesh_empty_scope_delta(before, after):
    unsafe = "(current_setting('app.current_tenant_id'::text, true))::uuid"
    safe = "(NULLIF(current_setting('app.current_tenant_id'::text, true), ''::text))::uuid"
    checked = 0
    for name, old_table in before['tables'].items():
        if not name.startswith('hypermesh_') or name not in after['tables']:
            continue
        old_policies = {row[0]: row for row in old_table['policies']}
        for row in after['tables'][name]['policies']:
            old = old_policies.get(row[0])
            if old is None:
                continue
            for index in (4, 5):
                if old[index] and unsafe in old[index]:
                    assert safe in row[index]
                    assert row[index].replace(safe, unsafe) == old[index]
                    row[index] = old[index]
                    checked += 1
    assert checked > 0
