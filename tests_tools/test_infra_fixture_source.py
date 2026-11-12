"""Keep the reused Infra fixture bytes tied to their reviewed source revision."""
import hashlib
import json
from pathlib import Path


def test_infra_fixture_sources_are_unchanged():
    root = Path(__file__).parents[1]/'scripts/infra-fixture'
    source = json.loads((root/'source.json').read_text())
    assert source['repository'] == 'FyberLabs/infra'
    assert source['revision'] == '41bd26250ef2f6f302ad88ba2cb6e4486f6769a7'
    assert set(source['files']) == {'nightly/postgres.py', 'ci_resources.py'}
    for name, digest in source['files'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest() == digest
