"""Refuse checkout-only histories and unsafe layers in the consumer image."""
import importlib.util
import io
import json
from pathlib import Path
import tarfile

import pytest

spec = importlib.util.spec_from_file_location('db_audit', Path(__file__).resolve().parents[1] / 'scripts/container_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


@pytest.mark.parametrize('name', ['controlplane_db/migrations.py',
    'controlplane_db/alembic/versions/0053.py',
    'controlplane_db/migration_chains/payment/baseline.sql',
    'controlplane_billing/stores.py'])
def test_checkout_and_hosted_files_refused(name):
    with pytest.raises(ValueError):
        audit.check_member(name, b'pass')


def test_layer_traversal_refused(tmp_path):
    inner = io.BytesIO()
    with tarfile.open(fileobj=inner, mode='w') as layer:
        member = tarfile.TarInfo('../escape')
        member.size = 1
        layer.addfile(member, io.BytesIO(b'x'))
    outer = tmp_path / 'image.tar'
    with tarfile.open(outer, 'w') as image:
        for name, data in {
            'manifest.json': json.dumps([{'Config': 'config.json', 'Layers': ['layer.tar']}]).encode(),
            'config.json': json.dumps({'config': {'User': '65532:65532'}}).encode(),
            'layer.tar': inner.getvalue(),
        }.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            image.addfile(member, io.BytesIO(data))
    with pytest.raises(ValueError, match='Unsafe layer'):
        audit.layers(outer, tmp_path / 'layers')
    assert not (tmp_path / 'escape').exists()
