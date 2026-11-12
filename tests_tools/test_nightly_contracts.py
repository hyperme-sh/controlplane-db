"""Offline regressions for scheduled qualification and failure reporting."""
import ast
import copy
import importlib.util
import os
from pathlib import Path
import subprocess

import pytest
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT/'qualification/history_tests'
spec = importlib.util.spec_from_file_location('contact_lane_contract', HISTORY/'contact_lane_contract.py')
contract = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contract)


def test_json_uses_one_bound_value_not_inline_boolean_parameters():
    tree = ast.parse((HISTORY/'test_financial_inventory.py').read_text())
    statement = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                     and any(isinstance(t, ast.Name) and t.id == 'SOURCE_FREE_UPDATE' for t in node.targets))
    assert set(text(ast.literal_eval(statement.args[0])).compile().params) == {'effects', 's'}


def contact():
    table = copy.deepcopy(contract.CONTACT_TABLE)
    table['grants'] = [['OWNER', p, False] for p in ('DELETE','INSERT','REFERENCES','SELECT','TRIGGER','TRUNCATE','UPDATE')]
    return {'tables': {'sociacl_contact_messages': table}}


def test_contact_delta_accepts_only_declared_schema_and_owner_grants():
    for maintain in (False, True):
        value = contact()
        if maintain: value['tables']['sociacl_contact_messages']['grants'].append(['OWNER','MAINTAIN',False])
        contract.assert_contact_lane_delta(value)
        assert value == {'tables': {}}
    for field in (*contract.CONTACT_TABLE, 'grants'):
        value = contact()
        value['tables']['sociacl_contact_messages'][field] = ['unexpected']
        with pytest.raises(AssertionError): contract.assert_contact_lane_delta(value)
    value = contact()
    value['tables']['sociacl_contact_messages']['grants'].append(['PUBLIC','SELECT',False])
    with pytest.raises(AssertionError): contract.assert_contact_lane_delta(value)


def test_schema_comparison_is_exact_and_bounded():
    expected = {'tables': {'unchanged': {'columns': ['x']}, 'changed': {'body': 'x'*100000}}}
    actual = copy.deepcopy(expected)
    contract.assert_same_schema(actual, expected)
    actual['tables']['changed']['body'] = 'private'*100000
    with pytest.raises(AssertionError, match=r'^Schema differs: tables.changed$'):
        contract.assert_same_schema(actual, expected)


def test_failed_history_exports_results_before_cleaning_scratch(tmp_path):
    tools = tmp_path/'bin'; tools.mkdir()
    stub = tools/'uv'
    stub.write_text('''#!/usr/bin/env python3
import pathlib,sys
args=sys.argv[1:]
for arg in args:
    if arg.startswith('--junitxml='):
        path=pathlib.Path(arg.split('=',1)[1])
        path.write_text('<testsuite><testcase name="stub"/></testsuite>')
        pathlib.Path(__file__).with_name('scratch').write_text(str(path.parent))
if 'qualification/history_tests' in args: sys.exit(7)
''')
    stub.chmod(0o700)
    output = tmp_path/'reports'
    result = subprocess.run(['bash', 'scripts/check-package.sh'], cwd=ROOT,
        env={**os.environ, 'PATH': str(tools)+os.pathsep+os.environ['PATH'],
             'TEST_DATABASE_URL': 'unused-by-stub', 'TEST_EVIDENCE_DIR': str(output)},
        capture_output=True, text=True, timeout=30)
    assert result.returncode == 7, result.stderr
    assert {p.name for p in output.iterdir()} == {'source.xml', 'history.xml'}
    assert not Path((tools/'scratch').read_text()).exists()
