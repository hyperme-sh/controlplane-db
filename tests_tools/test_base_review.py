import io
import json
from pathlib import Path
import sys
import tarfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from verify_base import verify_layers, verify, digest, installed_packages


def test_base_prefix_allows_consumer_layers_but_refuses_changed_base():
    manifest = {'diff_ids': ['a', 'b']}
    verify_layers({'rootfs': {'diff_ids': ['a', 'b', 'c']}}, manifest)
    with pytest.raises(ValueError):
        verify_layers({'rootfs': {'diff_ids': ['a', 'x']}}, manifest)


@pytest.fixture
def base(tmp_path):
    status = b'Package: example\nStatus: install ok installed\nVersion: 2\nSource: upstream (1)\n'
    path = tmp_path / 'var/lib/dpkg/status'
    path.parent.mkdir(parents=True)
    path.write_bytes(status)
    legal = tmp_path / 'usr/local/lib/python3.13/LICENSE.txt'
    legal.parent.mkdir(parents=True)
    legal.write_bytes(b'Python terms')
    sources = tmp_path / 'sources'
    sources.mkdir()
    archive = sources / 'Python-3.13.18.tar.xz'
    with tarfile.open(archive, 'w:xz') as stream:
        entry = tarfile.TarInfo('Python-3.13.18/LICENSE')
        entry.size = len(legal.read_bytes())
        stream.addfile(entry, io.BytesIO(legal.read_bytes()))
    manifest = {'publication_cleared': False, 'status_sha256': digest(status),
                'packages': installed_packages(status.decode()),
                'legal_sha256': {'usr/local/lib/python3.13/LICENSE.txt': digest(legal.read_bytes())},
                'python': {'version': '3.13.18', 'source_sha256': digest(archive.read_bytes())}}
    return tmp_path, manifest, sources


def test_exact_base_and_source_license_pairing(base):
    root, manifest, sources = base
    assert verify(root, manifest, sources)['base_packages'] == 1


@pytest.mark.parametrize('change', ['status', 'source-version', 'legal', 'escape', 'source'])
def test_changed_base_material_refuses(base, change):
    root, manifest, sources = base
    if change == 'status': (root / 'var/lib/dpkg/status').write_bytes(b'changed')
    if change == 'source-version': manifest['packages'][0]['source_version'] = 'other'
    if change == 'legal': (root / 'usr/local/lib/python3.13/LICENSE.txt').write_bytes(b'changed')
    if change == 'escape': manifest['legal_sha256'] = {'../outside': 'x'}
    if change == 'source': (sources / 'Python-3.13.18.tar.xz').write_bytes(b'changed')
    with pytest.raises(ValueError):
        verify(root, manifest, sources)


def test_source_version_defaults_to_binary_version():
    status = 'Package: example\nStatus: install ok installed\nVersion: 1:2-3\nSource: upstream\n'
    assert installed_packages(status)[0]['source_version'] == '1:2-3'


def test_dockerfile_keeps_the_reviewed_base():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / 'licenses/base-image.json').read_text())
    bases = [line.split()[1] for line in (root / 'deploy/Dockerfile.runtime').read_text().splitlines()
             if line.startswith('FROM ')]
    assert bases == [manifest['base'], manifest['base']]
