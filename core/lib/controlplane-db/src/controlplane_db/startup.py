"""Deployment startup selection; owner adoption is enabled by the test VM overlay."""
from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from controlplane_db import migrations


def _owners(database_url: str, root: Path = migrations._ROOT) -> None:
    registry = migrations._registry(root)
    engine = migrations._engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('controlplane-owner-migrations'))"))
            versions = migrations._versions(connection, root)
            legacy = migrations._legacy_revision(connection)
            tables = set(inspect(connection).get_table_names(schema='public'))
            expected = {table for entry in registry['chains'].values() for table in entry['tables']}
            if legacy is not None and legacy != registry['source_revision']:
                raise ValueError('upgrade the old chain to 0053_onboarding_runs before test reload')
            if all(value is None for value in versions.values()):
                if legacy is not None:
                    if not expected <= tables:
                        raise ValueError('mixed-chain database is missing baseline tables')
                    for chain, entry in registry['chains'].items():
                        command.stamp(migrations._config(root, chain, connection), entry['baseline'])
                elif expected.intersection(tables):
                    raise ValueError('unversioned existing tables require reviewed baseline adoption')
            elif any(value is None for value in versions.values()):
                raise ValueError('partial owner adoption requires review before test reload')
            for chain in migrations._ORDER:
                command.upgrade(migrations._config(root, chain, connection), 'head')
    finally:
        engine.dispose()


def main() -> int:
    mode = os.environ.get('CONTROLPLANE_MIGRATION_MODE', 'legacy')
    if mode == 'owners':
        url = os.environ.get('DATABASE_URL')
        if not url:
            raise ValueError('DATABASE_URL is required for owner adoption')
        _owners(url)
    elif mode == 'legacy':
        ini = Path(__file__).resolve().parents[2] / 'alembic.ini'
        command.upgrade(Config(str(ini)), 'head')
    else:
        raise ValueError('CONTROLPLANE_MIGRATION_MODE must be legacy or owners')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
