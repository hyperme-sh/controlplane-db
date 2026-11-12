"""Real PostgreSQL regression for temporary-view definer attacks and function ACL."""
import importlib.util
import os
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from controlplane_db import migrations, startup


@pytest.mark.parametrize('route', ['owner', 'legacy'])
def test_temp_view_cannot_execute_as_owner_and_public_has_no_access(route, monkeypatch):
    url = os.environ.get('TEST_DATABASE_URL')
    if not url:
        pytest.skip('requires disposable PostgreSQL TEST_DATABASE_URL')
    engine = create_engine(url)
    try:
        with engine.connect() as cx:
            tx = cx.begin()
            try:
                cx.execute(text('CREATE ROLE controlplane_app NOBYPASSRLS; CREATE ROLE share_untrusted NOBYPASSRLS'))
                cx.execute(text('CREATE TABLE public.sociacl_share_links(token_hash varchar(64), marker text)'))
                cx.execute(text("INSERT INTO public.sociacl_share_links VALUES ('valid', 'real')"))
                # Reproduce the historical definition without changing frozen source.
                cx.execute(text('''CREATE FUNCTION public.sociacl_share_lookup_by_hash(p_hash varchar)
                    RETURNS SETOF public.sociacl_share_links LANGUAGE sql STABLE SECURITY DEFINER
                    SET search_path = public AS $$ SELECT * FROM sociacl_share_links WHERE token_hash=p_hash LIMIT 1 $$'''))
                cx.execute(text('SET LOCAL ROLE controlplane_app'))
                cx.execute(text("CREATE TEMP VIEW sociacl_share_links AS SELECT 'valid'::varchar(64) AS token_hash, current_user::text AS marker"))
                # Negative control: the historical function resolves the attacker's view.
                assert cx.execute(text("SELECT marker FROM public.sociacl_share_lookup_by_hash('valid')")).scalar_one() == 'postgres'
                cx.execute(text('RESET ROLE'))
                if route == 'owner':
                    path = migrations._ROOT / 'platform/versions/0057_share_lookup_hardening.py'
                    spec = importlib.util.spec_from_file_location('hardening_revision', path)
                    revision = importlib.util.module_from_spec(spec); spec.loader.exec_module(revision)
                    with Operations.context(MigrationContext.configure(cx)):
                        revision.upgrade()
                        revision.upgrade()  # Safe repeat preserves grants/definition.
                else:
                    from contextlib import nullcontext
                    from types import SimpleNamespace
                    monkeypatch.setenv('CONTROLPLANE_MIGRATION_MODE', 'legacy')
                    monkeypatch.setattr(startup.command, 'upgrade', lambda *args: None)
                    monkeypatch.setattr(migrations, '_engine', lambda url: SimpleNamespace(begin=lambda: nullcontext(cx), dispose=lambda: None))
                    assert startup.main() == 0
                assert not cx.scalar(text("SELECT has_function_privilege('share_untrusted', 'public.sociacl_share_lookup_by_hash(varchar)', 'EXECUTE')"))
                assert cx.scalar(text("SELECT has_function_privilege('controlplane_app', 'public.sociacl_share_lookup_by_hash(varchar)', 'EXECUTE')"))
                cx.execute(text('SET LOCAL ROLE controlplane_app'))
                # If evaluated as the definer, this expression leaks its identity.
                assert cx.execute(text("SELECT marker FROM public.sociacl_share_lookup_by_hash('valid')")).scalar_one() == 'real'
                assert cx.execute(text("SELECT marker FROM public.sociacl_share_lookup_by_hash('missing')")).first() is None
                cx.execute(text('RESET ROLE; SET LOCAL ROLE share_untrusted'))
                with cx.begin_nested() as savepoint:
                    with pytest.raises(DBAPIError):
                        cx.execute(text("SELECT * FROM public.sociacl_share_lookup_by_hash('valid')"))
                    savepoint.rollback()
            finally:
                tx.rollback()
    finally:
        engine.dispose()


@pytest.mark.parametrize('mode', ['owners', 'legacy'])
def test_normal_startup_preserves_share_lookup_repair(mode, migration_db, monkeypatch):
    """Exercise deployment entry points, not a directly invoked repair revision."""
    engine = create_engine(migration_db)
    roles = ('controlplane', 'controlplane_app', 'share_startup_untrusted')
    created = []
    try:
        with engine.begin() as connection:
            for role in roles:
                # These names are the declared application roles. Refuse to
                # borrow an existing role from another fixture.
                assert not connection.scalar(text('SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:role)'), {'role': role})
                connection.exec_driver_sql(f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOBYPASSRLS')
            created.extend(roles)
        monkeypatch.setenv('DATABASE_URL', migration_db)
        monkeypatch.setenv('CONTROLPLANE_MIGRATION_MODE', mode)
        monkeypatch.setenv('CONTROLPLANE_DB_BOOTSTRAP', '1')
        assert startup.main() == 0
        assert startup.main() == 0
        with engine.begin() as connection:
            settings = connection.scalar(text("SELECT proconfig FROM pg_proc WHERE oid='public.sociacl_share_lookup_by_hash(varchar)'::regprocedure"))
            assert 'search_path=pg_catalog, public, pg_temp' in settings
            assert not connection.scalar(text("SELECT has_function_privilege('share_startup_untrusted', 'public.sociacl_share_lookup_by_hash(varchar)', 'EXECUTE')"))
            for role in roles[:2]:
                assert connection.scalar(text("SELECT has_function_privilege(:role, 'public.sociacl_share_lookup_by_hash(varchar)', 'EXECUTE')"), {'role': role})
                connection.exec_driver_sql(f'SET LOCAL ROLE "{role}"')
                # A vulnerable lookup would return this forged row even though
                # no corresponding share exists in the real table.
                connection.exec_driver_sql('''CREATE TEMP VIEW sociacl_share_links AS
                    SELECT (jsonb_populate_record(NULL::public.sociacl_share_links,
                        '{"token_hash":"startup-probe"}'::jsonb)).*''')
                assert connection.scalar(text("SELECT count(*) FROM public.sociacl_share_lookup_by_hash('startup-probe')")) == 0
                connection.exec_driver_sql('DROP VIEW pg_temp.sociacl_share_links')
                connection.exec_driver_sql('RESET ROLE')
            connection.exec_driver_sql('SET LOCAL ROLE share_startup_untrusted')
            with connection.begin_nested() as savepoint:
                with pytest.raises(DBAPIError):
                    connection.execute(text("SELECT * FROM public.sociacl_share_lookup_by_hash('startup-probe')"))
                savepoint.rollback()
    finally:
        try:
            with engine.begin() as connection:
                for role in reversed(created):
                    connection.exec_driver_sql(f'DROP OWNED BY "{role}"')
                    connection.exec_driver_sql(f'DROP ROLE "{role}"')
        finally:
            engine.dispose()
