import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    'verify_frozen_histories',
    Path(__file__).resolve().parents[1] / 'scripts/verify_frozen_histories.py',
)
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)


def test_frozen_histories_remain_in_the_checkout_and_out_of_the_wheel():
    manifest = verifier.verify(Path(__file__).resolve().parents[1])
    assert manifest['source_revision'] == '0053_onboarding_runs'
    assert 'platform_0053_baseline' == manifest['chains']['platform']['baseline']
