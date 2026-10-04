"""Explicit owner-chain upgrades and guarded 0053 baseline stamping.

Legacy startup continues using alembic.ini until an Ops-approved switch. The
runner never upgrades or stamps the mixed chain automatically.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from collections.abc import Sequence

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Connection

from controlplane_db.session import normalize_database_url

_ROOT = Path(__file__).with_name('migration_chains')
_ORDER = ('platform', 'events', 'hypermesh', 'aiuditor', 'payment_service')


def _registry(root: Path) -> dict:
    registry = json.loads((root / 'manifest.json').read_text())
    if tuple(registry['chains']) != _ORDER or registry['source_revision'] != '0053_onboarding_runs':
        raise ValueError('invalid owner migration registry')
    if any(entry['version_table'] != f'alembic_version_{chain}' for chain, entry in registry['chains'].items()):
        raise ValueError('invalid owner version table')
    return registry


def _config(root: Path, chain: str, connection: Connection | None = None) -> Config:
    registry = _registry(root)
    config = Config()
    config.set_main_option('script_location', str(root))
    config.set_main_option('path_separator', 'os')
    config.set_main_option('version_locations', str(root / chain / 'versions'))
    config.attributes['version_table'] = registry['chains'][chain]['version_table']
    if connection is not None:
        config.attributes['connection'] = connection
    return config


def chain_heads(registry_path: Path | None = None) -> dict[str, str]:
    """Return one current head for each owner, in apply order."""
    root = registry_path or _ROOT
    _registry(root)
    return {chain: ScriptDirectory.from_config(_config(root, chain)).get_current_head() for chain in _ORDER}


def _versions(connection: Connection, root: Path) -> dict[str, str | None]:
    registry = _registry(root)
    tables = set(inspect(connection).get_table_names(schema='public'))
    result = {}
    for chain, entry in registry['chains'].items():
        table = entry['version_table']
        if table not in tables:
            result[chain] = None
            continue
        revisions = list(connection.execute(text(f'SELECT version_num FROM public."{table}"')).scalars())
        if len(revisions) != 1:
            raise ValueError(f'{chain}: expected exactly one database head')
        result[chain] = revisions[0]
    return result


def _legacy_revision(connection: Connection) -> str | None:
    if not inspect(connection).has_table('alembic_version', schema='public'):
        return None
    revisions = list(connection.execute(text('SELECT version_num FROM public.alembic_version')).scalars())
    if len(revisions) != 1:
        raise ValueError('mixed chain must have exactly one revision')
    return revisions[0]


def _engine(database_url: str):
    url = normalize_database_url(database_url).replace('+asyncpg', '+psycopg')
    engine = create_engine(url)
    if engine.dialect.name != 'postgresql':
        engine.dispose()
        raise ValueError('owner migrations require PostgreSQL')
    return engine


def current_heads(database_url: str, registry_path: Path | None = None) -> dict[str, str | None]:
    """Read owner database revisions without changing schema or data."""
    engine = _engine(database_url)
    try:
        with engine.connect() as connection:
            return _versions(connection, registry_path or _ROOT)
    finally:
        engine.dispose()


def stamp_baselines(database_url: str, registry_path: Path | None = None) -> None:
    """Stamp all owners atomically only on a complete mixed-chain 0053 database."""
    root = registry_path or _ROOT
    registry = _registry(root)
    engine = _engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('controlplane-owner-migrations'))"))
            if _legacy_revision(connection) != registry['source_revision']:
                raise ValueError('upgrade the old chain to 0053_onboarding_runs before stamping')
            tables = set(inspect(connection).get_table_names(schema='public'))
            expected = {table for entry in registry['chains'].values() for table in entry['tables']}
            if not expected <= tables:
                raise ValueError('mixed-chain database is missing baseline tables')
            versions = _versions(connection, root)
            for chain, entry in registry['chains'].items():
                if versions[chain] not in (None, entry['baseline']):
                    raise ValueError(f'{chain}: refusing to overwrite a non-baseline head')
            for chain, entry in registry['chains'].items():
                command.stamp(_config(root, chain, connection), entry['baseline'])
    finally:
        engine.dispose()


def upgrade(database_url: str, chains: Sequence[str] | None = None, registry_path: Path | None = None, *, baseline_only: bool = False) -> None:
    """Upgrade requested owners in fixed order; legacy databases require stamping."""
    root = registry_path or _ROOT
    registry = _registry(root)
    requested = set(chains) if chains is not None else set(_ORDER)
    if not requested or requested - set(_ORDER):
        raise ValueError('select at least one known owner chain')
    heads = chain_heads(root)
    engine = _engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('controlplane-owner-migrations'))"))
            versions = _versions(connection, root)
            legacy = _legacy_revision(connection)
            if legacy is not None and (legacy != registry['source_revision'] or any(value is None for value in versions.values())):
                raise ValueError('mixed-chain databases require explicit 0053 baseline stamping')
            # Never use an upgrade to adopt an unversioned pre-existing schema.
            existing = set(inspect(connection).get_table_names(schema='public'))
            for chain in requested:
                if versions[chain] is None and existing.intersection(registry['chains'][chain]['tables']):
                    raise ValueError(f'{chain}: existing tables require reviewed baseline adoption')
            if requested.intersection({'hypermesh', 'aiuditor'}) and 'platform' not in requested:
                if versions['platform'] != heads['platform']:
                    raise ValueError('upgrade platform before product chains')
            for chain in _ORDER:
                if chain in requested:
                    target = registry['chains'][chain]['baseline'] if baseline_only else 'head'
                    command.upgrade(_config(root, chain, connection), target)
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('heads', 'current', 'upgrade', 'stamp'))
    parser.add_argument('--chain', action='append')
    parser.add_argument('--baseline-only', action='store_true')
    args = parser.parse_args()
    if (args.chain or args.baseline_only) and args.action != 'upgrade':
        parser.error('--chain and --baseline-only are only supported for upgrade')
    if args.action == 'heads':
        print(json.dumps(chain_heads(), sort_keys=True))
        return 0
    url = os.environ.get('DATABASE_URL')
    if not url:
        parser.error('DATABASE_URL is required')
    if args.action == 'current':
        print(json.dumps(current_heads(url), sort_keys=True))
    elif args.action == 'stamp':
        stamp_baselines(url)
    else:
        upgrade(url, args.chain, baseline_only=args.baseline_only)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
