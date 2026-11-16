#!/usr/bin/env bash
# CI-only import contracts: no service, database or external network is started.
set -euo pipefail
image=${1:?Prepared image required}
scratch=$(mktemp -d "${RUNNER_TEMP:-/tmp}/db-replacement.XXXXXX")
container=
cleanup() { if [[ -n "$container" ]]; then docker rm "$container" >/dev/null; fi; rm -rf -- "$scratch"; }
trap cleanup EXIT
container=$(docker create "$image")
site=/opt/db/lib/python3.13/site-packages
docker cp "$container:$site/psycopg" "$scratch/psycopg"
docker cp "$container:$site/psycopg_binary" "$scratch/psycopg_binary"
docker cp "$container:$site/psycopg_binary.libs" "$scratch/psycopg_binary.libs"
printf '\nreplacement_contract_marker = True\n' >> "$scratch/psycopg/__init__.py"
# Unused trailing bytes preserve the ABI while proving modified files can load.
python3 - "$scratch" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
libraries = list((root / 'psycopg_binary').glob('*.so'))
assert libraries, 'Missing native extensions'
libpq, = (root / 'psycopg_binary.libs').glob('libpq-*.so.*')
for library in [*libraries, libpq]:
    with library.open('ab') as stream:
        stream.write(b'\0recipient-replacement-contract\0')
PY
chmod -R a+rX "$scratch"
docker run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges \
  --mount "type=bind,src=$scratch/psycopg,dst=$site/psycopg,readonly" \
  --mount "type=bind,src=$scratch/psycopg_binary,dst=$site/psycopg_binary,readonly" \
  --mount "type=bind,src=$scratch/psycopg_binary.libs,dst=$site/psycopg_binary.libs,readonly" \
  --entrypoint /opt/db/bin/python "$image" -I -c \
  'import psycopg; assert psycopg.replacement_contract_marker; assert psycopg.pq.__impl__ == "binary"; assert psycopg.pq.version() == 180006; print("Modified psycopg package, extensions and libpq loaded")'
