#!/usr/bin/env python3
"""Lock frozen migration histories to the bytes recorded in the owner manifest."""
import hashlib
import json
from pathlib import Path
import sys
import tomllib

sys.path.insert(0, str(Path(__file__).resolve().parent))
from runtime_surface import HATCH_EXCLUDES, HISTORY_PREFIXES, WHEEL_EXCLUDED, is_wheel_excluded


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root):
    root = Path(root)
    chains = root / 'src/controlplane_db/migration_chains'
    manifest_path = chains / 'manifest.json'
    if not manifest_path.is_file():
        raise ValueError('frozen owner manifest is missing from the checkout')
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('source_revision') != '0053_onboarding_runs':
        raise ValueError('frozen manifest no longer records mixed-chain 0053')
    alembic = root / 'src/controlplane_db/alembic'
    frozen = manifest.get('frozen_legacy') or {}
    if not frozen:
        raise ValueError('frozen mixed-chain inventory is empty')
    for rel, expected in sorted(frozen.items()):
        path = alembic / rel
        if not path.is_file():
            raise ValueError(f'missing frozen mixed-chain file: {path.relative_to(root)}')
        actual = _digest(path)
        if actual != expected:
            raise ValueError(f'{path.relative_to(root)} differs from the frozen digest')
    head = alembic / 'versions/20261001_0053_onboarding_runs.py'
    if not head.is_file() or _digest(head) != frozen['versions/20261001_0053_onboarding_runs.py']:
        raise ValueError('mixed chain through 0053 is not the frozen revision')
    owners = manifest.get('chains') or {}
    if not owners:
        raise ValueError('frozen owner baseline inventory is empty')
    for name, entry in sorted(owners.items()):
        baseline = chains / name / 'versions/0053_baseline.py'
        sql = chains / name / 'versions/baseline.sql'
        if not baseline.is_file():
            raise ValueError(f'missing frozen owner baseline: {baseline.relative_to(root)}')
        if not sql.is_file():
            raise ValueError(f'missing frozen owner baseline SQL: {sql.relative_to(root)}')
        if _digest(sql) != entry.get('baseline_sha256'):
            raise ValueError(f'{sql.relative_to(root)} differs from the frozen baseline digest')
        if entry.get('baseline') != f'{name}_0053_baseline':
            raise ValueError(f'{name} baseline revision was renamed')
    for rel in (
        'src/controlplane_db/alembic.ini',
        'src/controlplane_db/migrations.py',
        'src/controlplane_db/startup.py',
        'src/controlplane_db/_share_lookup_hardening.py',
        'qualification/history_tests/test_owner_migration_chains.py',
        'qualification/history_tests/migration_test_support.py',
        'src/controlplane_db/test_retention.py',
    ):
        if not (root / rel).is_file():
            raise ValueError(f'missing checkout qualification file: {rel}')
    project = tomllib.loads((root / 'pyproject.toml').read_text())
    targets = project['tool']['hatch']['build']['targets']
    for kind in ('wheel', 'sdist'):
        excluded = set(targets[kind].get('exclude', []))
        missing = [pattern for pattern in HATCH_EXCLUDES if pattern not in excluded]
        if missing:
            raise ValueError(f'{kind} still ships frozen histories: {missing}')
    for path in (root / 'src').rglob('*'):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        rel = path.relative_to(root / 'src').as_posix()
        if rel.startswith(('controlplane_db/migration_chains/', 'controlplane_db/alembic/')) and not is_wheel_excluded(rel):
            raise ValueError(f'frozen history would ship in the runtime wheel: {rel}')
    if not any(prefix.startswith('controlplane_db/migration_chains') for prefix in HISTORY_PREFIXES):
        raise ValueError('owner chains are no longer classified as checkout history')
    if not any(name.endswith('migrations.py') for name in WHEEL_EXCLUDED):
        raise ValueError('checkout migration runner would ship in the shared wheel')
    return manifest


if __name__ == '__main__':
    verify(Path(__file__).resolve().parents[1])
    print('Frozen mixed chain and owner baselines match the recorded checkout digests')
