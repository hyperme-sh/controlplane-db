"""Installed migration resources must resolve without a source checkout."""
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from controlplane_db import migrations, startup


def test_installed_legacy_startup_uses_packaged_config(monkeypatch):
    monkeypatch.setenv('CONTROLPLANE_MIGRATION_MODE', 'legacy')
    seen = []
    def upgrade(config, target):
        path = Path(config.config_file_name)
        assert path.parent == Path(startup.__file__).parent
        assert path.is_file()
        assert target == 'head'
        seen.append(ScriptDirectory.from_config(config).get_current_head())
    monkeypatch.setattr(startup.command, 'upgrade', upgrade)
    assert startup.main() == 0
    assert seen == ['0053_onboarding_runs']


@pytest.mark.parametrize('chain', migrations._ORDER)
def test_owner_graph_has_one_head_and_frozen_baseline(chain):
    registry = migrations._registry(migrations._ROOT)
    script = ScriptDirectory.from_config(migrations._config(migrations._ROOT, chain))
    head, = script.get_heads()
    revisions = list(script.walk_revisions())
    assert head == migrations.chain_heads()[chain]
    assert registry['chains'][chain]['baseline'] in {r.revision for r in revisions}
    assert len({r.revision for r in revisions}) == len(revisions)
    baseline = migrations._ROOT / chain / 'versions/baseline.sql'
    assert baseline.is_file() and baseline.stat().st_size > 0
    assert registry['chains'][chain]['version_table'] == f'alembic_version_{chain}'
