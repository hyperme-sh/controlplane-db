"""Accept only the official Python public signing fingerprint in image metadata."""
import json
from pathlib import Path
import sys

FINGERPRINT = '7169605F62C751356D054A26A821E680E5FA6305'

def known(finding, layers):
    return (Path(finding['File']).resolve() == (layers / 'image-config.json').resolve()
            and finding['RuleID'] == 'generic-api-key'
            and finding.get('Secret') == FINGERPRINT)

if __name__ == '__main__':
    rows = json.loads(Path(sys.argv[1]).read_text())
    unexpected = [r for r in rows if not known(r, Path(sys.argv[2]))]
    print(json.dumps({'public_fingerprint_matches': len(rows)-len(unexpected), 'unexpected': len(unexpected)}))
    for row in unexpected:
        print({k: row.get(k) for k in ('File', 'StartLine', 'RuleID')})
    raise SystemExit(bool(unexpected))
