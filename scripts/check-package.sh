#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
unset PYTHONPATH UV_NO_SYNC
python3 - <<'PY'
import subprocess, sys
from pathlib import Path
sys.path.insert(0, 'scripts')
from runtime_surface import open_surface_files
files = [str(path) for path in open_surface_files(Path('.').resolve())]
raise SystemExit(subprocess.call([sys.executable, 'scripts/check_open_boundary.py', 'pyproject.toml', *files]))
PY
mode="${1:-fixtures}"
case "$mode" in
  --contracts) test_dir=tests_contracts ;;
  fixtures) test_dir=tests; : "${TEST_DATABASE_URL:?A disposable PostgreSQL server is required}" ;;
  *) echo 'Use --contracts for offline package checks, or no argument for nightly PostgreSQL' >&2; exit 2 ;;
esac
uv lock --check
uv sync --frozen --python 3.13
scratch=$(mktemp -d)
finish_checks() {
  local status=$?
  trap - EXIT
  shopt -s nullglob
  local reports=("$scratch"/*.xml)
  if [[ -n "${TEST_EVIDENCE_DIR:-}" && ${#reports[@]} -gt 0 ]]; then
    mkdir -p "$TEST_EVIDENCE_DIR" && cp "${reports[@]}" "$TEST_EVIDENCE_DIR/" || status=1
  fi
  rm -rf "$scratch" || status=1
  exit "$status"
}
trap finish_checks EXIT
uv run --frozen pytest "$test_dir" --junitxml="$scratch/source.xml"
uv run --frozen pytest -q tests_tools
# Frozen histories are checkout qualification, not installed-package cases.
if [[ "$mode" == --contracts ]]; then
  uv run --frozen pytest -q qualification/history_tests/test_owner_startup_ahead.py
else
  uv run --frozen pytest -q qualification/history_tests --junitxml="$scratch/history.xml"
  uv run --frozen pytest -q qualification/storage_tests --junitxml="$scratch/storage.xml"
fi
uv build --out-dir "$scratch/dist"
uv run --frozen python scripts/verify_wheel.py "$scratch/dist"
uv run --frozen python scripts/export_release_contract.py "$scratch"/dist/*.whl --output "$scratch/contract"
for qualified_manifest in releases/qualification/current/release.json releases/candidate/release.json; do
if [[ -f "$qualified_manifest" ]]; then
  uv run --frozen python scripts/verify_release_candidate.py "$qualified_manifest" "$scratch/contract/contract.json" "$scratch/contract/evidence.json" controlplane-db
fi
done
uv export --frozen --no-emit-project --format requirements-txt --output-file "$scratch/requirements.txt" >/dev/null
uv venv --python 3.13 "$scratch/venv"
uv pip sync --python "$scratch/venv/bin/python" "$scratch/requirements.txt"
uv pip install --python "$scratch/venv/bin/python" --constraint "$scratch/requirements.txt" "$scratch"/dist/*.whl
cp -R "$test_dir" "$scratch/tests"
(cd "$scratch" && "$scratch/venv/bin/python" -I -m pytest -c /dev/null tests --junitxml="$scratch/wheel.xml")
# Rebuild from the sdist; a checkout must not supply omitted package files.
uv run --frozen python - "$scratch" <<'PY'
import pathlib, sys, tarfile
root = pathlib.Path(sys.argv[1])
with tarfile.open(next((root / 'dist').glob('*.tar.gz'))) as archive:
    archive.extractall(root / 'sdist', filter='data')
PY
uv build --wheel "$scratch"/sdist/* --out-dir "$scratch/rebuilt"
uv run --frozen python scripts/verify_wheel.py "$scratch/rebuilt"
uv run --frozen python scripts/export_release_contract.py "$scratch"/rebuilt/*.whl --output "$scratch/rebuilt-contract"
cmp "$scratch/contract/contract.json" "$scratch/rebuilt-contract/contract.json"
uv pip install --python "$scratch/venv/bin/python" --constraint "$scratch/requirements.txt" --reinstall "$scratch"/rebuilt/*.whl
uv pip check --python "$scratch/venv/bin/python"
(cd "$scratch" && "$scratch/venv/bin/python" -I -m pytest -c /dev/null tests --junitxml="$scratch/sdist.xml")

# Retain the exact validated bytes for the release channel; never rebuild them.
if [[ -n "${RELEASE_ARTIFACT_DIR:-}" ]]; then
  mkdir -p "$RELEASE_ARTIFACT_DIR"
  cp "$scratch/dist"/* "$RELEASE_ARTIFACT_DIR/"
fi

python3 scripts/verify-test-results.py "$scratch/source.xml" "$scratch/wheel.xml" "$scratch/sdist.xml"
