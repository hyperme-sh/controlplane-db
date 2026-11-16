"""Verify pinned base layers, installed legal bytes and CPython source pairing."""
import argparse
import hashlib
import json
import re
from email.parser import Parser
from pathlib import Path
import tarfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def installed_packages(status):
    rows = []
    for paragraph in status.strip().split('\n\n'):
        record = Parser().parsestr(paragraph)
        if record.get('Status') != 'install ok installed':
            continue
        package, version = record['Package'], record['Version']
        source = record.get('Source', package)
        match = re.fullmatch(r'([^ ()]+)(?: \(([^()]+)\))?', source)
        if not package or not version or not match:
            raise ValueError('Malformed installed package record')
        rows.append({'package': package, 'version': version,
                     'source': match[1], 'source_version': match[2] or version})
    if not rows or len({row['package'] for row in rows}) != len(rows):
        raise ValueError('Empty or duplicate installed package inventory')
    return sorted(rows, key=lambda row: row['package'])


def verify(root, manifest, sources):
    if manifest['publication_cleared'] is not False:
        raise ValueError('Base publication must remain uncleared')
    if digest((root / 'var/lib/dpkg/status').read_bytes()) != manifest['status_sha256']:
        raise ValueError('Base installed package inventory changed')
    keys = ('package', 'version', 'source', 'source_version')
    expected_packages = sorted([{key: row[key] for key in keys} for row in manifest['packages']],
                               key=lambda row: row['package'])
    if installed_packages((root / 'var/lib/dpkg/status').read_text()) != expected_packages:
        raise ValueError('Base source-version inventory differs from installed packages')
    for path, expected in manifest['legal_sha256'].items():
        resolved = (root / path).resolve()
        if not resolved.is_relative_to(root.resolve()) or digest(resolved.read_bytes()) != expected:
            raise ValueError('Base legal text changed: ' + path)
    record = manifest['python']
    archive = sources / ('Python-' + record['version'] + '.tar.xz')
    if digest(archive.read_bytes()) != record['source_sha256']:
        raise ValueError('CPython source changed')
    with tarfile.open(archive) as stream:
        member = stream.getmember('Python-' + record['version'] + '/LICENSE')
        if not member.isfile() or member.size > 1024 * 1024:
            raise ValueError('Invalid CPython license member')
        if digest(stream.extractfile(member).read()) != manifest['legal_sha256']['usr/local/lib/python3.13/LICENSE.txt']:
            raise ValueError('CPython source/license pairing changed')
    return {'base_packages': len(manifest['packages']), 'legal_files': len(manifest['legal_sha256']), 'publication_cleared': False}


def verify_layers(config, manifest):
    expected = manifest['diff_ids']
    if not expected or config['rootfs']['diff_ids'][:len(expected)] != expected:
        raise ValueError('Prepared image does not retain the reviewed base layers')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['installed', 'layers'])
    parser.add_argument('manifest', type=Path)
    parser.add_argument('path', type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    if args.mode == 'layers':
        verify_layers(json.loads(args.path.read_text()), manifest)
    else:
        print(json.dumps(verify(Path('/'), manifest, args.path)))
