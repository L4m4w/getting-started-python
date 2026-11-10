#!/bin/sh
set -eu
cd "$(CDPATH= cd "$(dirname "$0")/.." && pwd)"
[ "$#" -eq 0 ] || { echo 'Usage: sh tools/compile-tests.sh' >&2; exit 64; }
runner=${PYTHON:-python3}
"$runner" - <<'CHECK'
import ast
from pathlib import Path
files = [Path('conftest.py'), Path('notify_telegram.py')]
files += sorted(Path('pages').rglob('*.py')) + sorted(Path('tests').rglob('*.py'))
for path in files:
    ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
print(f'Syntax OK: {len(files)} Python files; no UI executed.')
CHECK
"$runner" -m pytest --collect-only -q
printf '%s\n' 'Collection completed; no browser scenarios executed.'
