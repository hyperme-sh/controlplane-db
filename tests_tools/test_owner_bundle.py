import importlib.util
import io
import tarfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('install_owner_bundle', Path(__file__).resolve().parents[1] / 'scripts/install_owner_bundle.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def sdist(tmp_path):
    files = {
        'controlplane_db-0.1.0/src/controlplane_db/__init__.py': b'runtime\n',
        'controlplane_db-0.1.0/src/controlplane_db/alembic.ini': b'[alembic]\n',
        'controlplane_db-0.1.0/src/controlplane_db/alembic/env.py': b'env\n',
        'controlplane_db-0.1.0/src/controlplane_db/migration_chains/manifest.json': b'{}\n',
        'controlplane_db-0.1.0/src/controlplane_db/migrations.py': b'not a bundle file\n',
        'controlplane_db-0.1.0/src/controlplane_db/alembic/../escape.py': b'escape\n',
    }
    path = tmp_path / 'package.tar.gz'
    with tarfile.open(path, 'w:gz') as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return path


def package(tmp_path):
    directory = tmp_path / 'venv' / 'lib' / 'python3.13' / 'site-packages' / 'controlplane_db'
    directory.mkdir(parents=True)
    (directory / '__init__.py').write_text('installed\n')
    return directory


def test_installs_only_owner_bundle_beside_runtime_package(tmp_path):
    directory = package(tmp_path)
    count = installer.install(sdist(tmp_path), directory)
    assert count == 3
    assert (directory / 'alembic.ini').read_bytes() == b'[alembic]\n'
    assert (directory / 'alembic' / 'env.py').read_bytes() == b'env\n'
    assert (directory / 'migration_chains' / 'manifest.json').read_bytes() == b'{}\n'
    assert not (directory / 'migrations.py').exists()
    assert not (directory / 'escape.py').exists()
    assert (directory / '__init__.py').read_text() == 'installed\n'


def test_replaces_a_previously_installed_bundle(tmp_path):
    directory = package(tmp_path)
    stale = directory / 'migration_chains' / 'versions' / 'old.py'
    stale.parent.mkdir(parents=True)
    stale.write_text('stale\n')
    installer.install(sdist(tmp_path), directory)
    assert not stale.exists()
    assert (directory / 'migration_chains' / 'manifest.json').is_file()


def test_refuses_to_write_into_a_checkout(tmp_path):
    directory = tmp_path / 'src' / 'controlplane_db'
    directory.mkdir(parents=True)
    (directory / '__init__.py').write_text('source\n')
    with pytest.raises(ValueError):
        installer.install(sdist(tmp_path), directory)
