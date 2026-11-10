#!/bin/sh
set -eu

cd "$(CDPATH= cd "$(dirname "$0")/.." && pwd)"

usage() { printf "%s\n" "Usage: sh tools/git.sh status|diff|check" >&2; exit 64; }
[ "$#" -eq 1 ] || usage
export GIT_OPTIONAL_LOCKS=0
case "$1" in
  status)
    printf '%s\n' '+ git --no-pager -c core.fsmonitor=false status --short -- .'
    git --no-pager -c core.fsmonitor=false status --short -- .
    ;;
  diff)
    printf '%s\n' '+ git --no-pager -c core.fsmonitor=false diff --no-ext-diff --no-textconv -- .'
    git --no-pager -c core.fsmonitor=false diff --no-ext-diff --no-textconv -- .
    printf '%s\n' '+ git --no-pager -c core.fsmonitor=false diff --cached --no-ext-diff --no-textconv -- .'
    git --no-pager -c core.fsmonitor=false diff --cached --no-ext-diff --no-textconv -- .
    ;;
  check)
    printf '%s\n' '+ git --no-pager -c core.fsmonitor=false diff --check --no-ext-diff --no-textconv -- .'
    git --no-pager -c core.fsmonitor=false diff --check --no-ext-diff --no-textconv -- .
    printf '%s\n' '+ git --no-pager -c core.fsmonitor=false diff --cached --check --no-ext-diff --no-textconv -- .'
    git --no-pager -c core.fsmonitor=false diff --cached --check --no-ext-diff --no-textconv -- .
    ;;
  *) usage ;;
esac
