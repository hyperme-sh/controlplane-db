"""Boundary between the shared runtime wheel and checkout-only migration history."""
from pathlib import Path

# Frozen mixed chain and owner baselines. Their SQL names historical provider
# tables, so they are qualification sources rather than the open runtime surface.
HISTORY_PREFIXES = (
    'controlplane_db/alembic.ini',
    'controlplane_db/alembic/',
    'controlplane_db/migration_chains/',
)

# Checkout-only runner and the helper revision 0081 imports. Neither is part of
# the shared runtime wheel. The helper names historical provider columns.
RUNNER_FILES = (
    'controlplane_db/migrations.py',
    'controlplane_db/startup.py',
    'controlplane_db/_share_lookup_hardening.py',
    'controlplane_db/test_retention.py',
)

WHEEL_EXCLUDED = HISTORY_PREFIXES + RUNNER_FILES

# Open-surface scan covers the runner modules except the helper, whose SQL
# records historical provider column names and is not shipped.
UNSCANNED = HISTORY_PREFIXES + ('controlplane_db/test_retention.py',)

HATCH_EXCLUDES = (
    'src/controlplane_db/alembic/**',
    'src/controlplane_db/alembic.ini',
    'src/controlplane_db/migration_chains/**',
    'src/controlplane_db/migrations.py',
    'src/controlplane_db/startup.py',
    'src/controlplane_db/_share_lookup_hardening.py',
    'src/controlplane_db/test_retention.py',
)


def _matches(name, prefixes):
    return any(name == path or (path.endswith('/') and name.startswith(path))
               for path in prefixes)


def is_wheel_excluded(name):
    return _matches(name, WHEEL_EXCLUDED)


def iter_source_files(root):
    src = Path(root) / 'src'
    if not src.is_dir():
        raise ValueError(f'missing open surface: {src}')
    for path in sorted(src.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            yield path, path.relative_to(src).as_posix()


def open_surface_files(root):
    """Runtime files the open-boundary scan must cover.

    Frozen histories stay on disk and out of this list. The checkout-only
    runner remains in the scan so provider symbols cannot hide there.
    """
    files = [path for path, rel in iter_source_files(root) if not _matches(rel, UNSCANNED)]
    if not files:
        raise ValueError('missing open surface')
    return files
