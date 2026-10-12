"""Deployment startup selection; owner adoption is enabled by the test VM overlay.

Owners mode keeps booting when a chain's database revision is ahead of this
image. Migrations are expand-only, so an N-1 image must run on an N schema
and this path leaves that newer schema in place.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.script.revision import ResolutionError
from alembic.util.exc import CommandError
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection

from controlplane_db import migrations

_logger = logging.getLogger(__name__)


def _revision_missing_from_image(script: ScriptDirectory, revision: str) -> bool:
    """True only when Alembic cannot find this database revision in the image.

    ``upgrade`` reports that as ``Can't locate revision identified by '<id>'``
    with a ``ResolutionError`` cause of ``No such revision or branch``. A known
    revision, including one that is behind head, resolves and must still
    upgrade. Any other resolution error, including an ambiguous prefix, raises.
    """
    try:
        script.get_revision(revision)
    except CommandError as exc:
        cause = exc.__cause__
        missing = (
            str(exc) == f"Can't locate revision identified by '{revision}'"
            and isinstance(cause, ResolutionError)
            and str(cause).startswith(f"No such revision or branch '{revision}'")
        )
        if missing:
            return True
        raise
    return False


def _upgrade_owner_chain(root: Path, chain: str, connection: Connection, revision: str | None) -> None:
    """Upgrade one owner chain unless its database revision is ahead of this image."""
    if revision is not None:
        script = ScriptDirectory.from_config(migrations._config(root, chain))
        if _revision_missing_from_image(script, revision):
            _logger.warning(
                'skipping %s upgrade: database revision %s is not in this image (image head %s)',
                chain,
                revision,
                script.get_current_head(),
            )
            return
    command.upgrade(migrations._config(root, chain, connection), 'head')


def _owners(database_url: str, root: Path | None = None) -> None:
    if root is None:
        root = migrations._ROOT
    registry = migrations._registry(root)
    engine = migrations._engine(database_url)
    try:
        with engine.begin() as connection:
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtext('controlplane-owner-migrations'))"))
            versions = migrations._versions(connection, root)
            legacy = migrations._legacy_revision(connection)
            tables = set(inspect(connection).get_table_names(schema='public'))
            current_tables = {table for entry in registry['chains'].values() for table in entry['tables']}
            expected = {table for entry in registry['chains'].values()
                        for table in entry.get('baseline_tables', entry['tables'])}
            if legacy is not None and legacy != registry['source_revision']:
                raise ValueError('upgrade the old chain to 0053_onboarding_runs before test reload')
            if all(value is None for value in versions.values()):
                if legacy is not None:
                    if not expected <= tables:
                        raise ValueError('mixed-chain database is missing baseline tables')
                    for chain, entry in registry['chains'].items():
                        command.stamp(migrations._config(root, chain, connection), entry['baseline'])
                elif current_tables.intersection(tables):
                    raise ValueError('unversioned existing tables require reviewed baseline adoption')
            elif any(value is None for value in versions.values()):
                raise ValueError('partial owner adoption requires review before test reload')
            for chain in migrations._ORDER:
                _upgrade_owner_chain(root, chain, connection, versions[chain])
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
