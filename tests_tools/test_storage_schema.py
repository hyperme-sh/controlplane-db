"""Offline storage bundle input and packaging boundaries."""
import importlib.util
from pathlib import Path
import tomllib
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('storage_migrate',ROOT/'storage-schema/migrate.py')
migrate=importlib.util.module_from_spec(spec);spec.loader.exec_module(migrate)


@pytest.mark.parametrize('value',['','Upper','x;DROP SCHEMA public','a.b','a'*64,None])
def test_schema_names_are_bounded_identifiers(value):
    with pytest.raises(ValueError): migrate.name(value)


def test_storage_bundle_is_source_only_and_uses_declared_ids():
    project=tomllib.loads((ROOT/'pyproject.toml').read_text())
    assert 'storage-schema' in project['tool']['hatch']['build']['targets']['sdist']['include']
    assert project['tool']['hatch']['build']['targets']['wheel']['packages']==['src/controlplane_db']
    assert migrate.name('storage_owner')=='storage_owner'
    text=migrate.DDL.read_text()
    assert 'INSERT INTO tenants' not in text
    assert 'FORCE ROW LEVEL SECURITY' in text
