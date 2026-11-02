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
