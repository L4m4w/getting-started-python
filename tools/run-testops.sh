#!/bin/sh
. "$(dirname "$0")/_python.sh"
exec "$harness_python" tools/testops.py "$@"
