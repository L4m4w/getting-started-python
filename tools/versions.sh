#!/bin/sh
set -eu
cd "$(CDPATH= cd "$(dirname "$0")/.." && pwd)"
[ "$#" -le 1 ] || { echo 'Usage: sh tools/versions.sh [local|actions|jenkins]' >&2; exit 64; }
case "${1:-local}" in local|actions|jenkins) ;; *) exit 64 ;; esac
runner=${PYTHON:-python3}
"$runner" - "${1:-local}" <<'CHECK'
import sys
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
profile=sys.argv[1]
allowed={'actions': {(3,13)}, 'jenkins': {(3,14)}, 'local': {(3,13),(3,14)}}[profile]
errors=[]
print(f'Python {sys.version.split()[0]}; profile={profile}')
if sys.version_info[:2] not in allowed:
    errors.append('Interpreter outside the documented target matrix')
for line in Path('requirements.txt').read_text().splitlines():
    line=line.strip()
    if not line or line.startswith('#'):
        continue
    name, expected=line.split('==',1)
    try:
        actual=version(name)
    except PackageNotFoundError:
        actual='MISSING'
    print(f'{name}: expected={expected}, actual={actual}')
    if actual != expected:
        errors.append(f'{name} version mismatch')
for error in errors:
    print(error, file=sys.stderr)
print('Browser, driver, SUT and external integrations: NOT_VERIFIED')
sys.exit(69 if errors else 0)
CHECK
