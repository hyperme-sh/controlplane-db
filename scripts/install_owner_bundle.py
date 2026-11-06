"""Install owner migration resources beside a runtime wheel.

The shared wheel omits alembic.ini, the frozen mixed chain, and migration_chains.
An owner image installs that bundle from the sdist. The wheel bytes stay unchanged.
"""
import argparse
import shutil
import tarfile
from pathlib import Path

BUNDLE = ('alembic.ini', 'alembic', 'migration_chains')


def bundle_relative(name):
    marker = 'src/controlplane_db/'
    index = name.find(marker)
    if index == -1:
        return None
    relative = name[index + len(marker):]
    if not relative or relative.endswith('/') or '..' in Path(relative).parts or relative.startswith('/'):
        return None
    if relative.split('/', 1)[0] not in BUNDLE:
        return None
    return relative


def install(sdist, package_dir):
    package_dir = Path(package_dir).resolve()
    if package_dir.name != 'controlplane_db' or 'site-packages' not in package_dir.parts:
        raise ValueError('Refusing to install the owner bundle outside site-packages')
    if not (package_dir / '__init__.py').is_file():
        raise ValueError('Runtime package is not installed')
    with tarfile.open(sdist) as archive:
        selected = []
        for member in archive.getmembers():
            relative = bundle_relative(member.name)
            if relative is None:
                continue
            if member.issym() or member.islnk():
                raise ValueError('Owner bundle contains a link')
            if member.isfile():
                selected.append((member, relative))
        found = {relative.split('/', 1)[0] for _, relative in selected}
        missing = [name for name in BUNDLE if name not in found]
        if missing:
            raise ValueError('Sdist is missing owner migration resources: ' + ', '.join(missing))
        for name in BUNDLE:
            target = package_dir / name
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
        for member, relative in selected:
            destination = package_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ValueError(f'Owner bundle member is not a file: {relative}')
            destination.write_bytes(extracted.read())
    return len(selected)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sdist', type=Path)
    parser.add_argument('package_dir', type=Path)
    args = parser.parse_args()
    count = install(args.sdist, args.package_dir)
    print(f'Installed {count} owner migration resources beside the runtime package')
