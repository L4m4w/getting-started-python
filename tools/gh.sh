#!/bin/sh
set -eu

cd "$(CDPATH= cd "$(dirname "$0")/.." && pwd)"

usage() { printf "%s\n" "Usage: sh tools/gh.sh runs | view N | view-log N | --allow-ci-write rerun N | --allow-ci-write dispatch" >&2; exit 64; }
allow_write=false
if [ "${1-}" = "--allow-ci-write" ]; then allow_write=true; shift; fi
case "${1-}" in
  runs|dispatch) [ "$#" -eq 1 ] || usage ;;
  view|view-log|rerun) [ "$#" -eq 2 ] || usage ;;
  *) usage ;;
esac
case "$1" in
  rerun|dispatch)
    [ "$allow_write" = true ] || { printf "%s\n" "BLOCKED: approve CI write — run with --allow-ci-write." >&2; exit 77; } ;;
esac
case "${2-}" in ""|*[!0-9]*) [ "$1" = runs ] || [ "$1" = dispatch ] || usage ;; esac
missing=""
[ -n "${GH_TOKEN:-}" ] || missing="$missing GH_TOKEN"
[ -n "${GITHUB_REPOSITORY:-}" ] || missing="$missing GITHUB_REPOSITORY"
[ -z "$missing" ] || { printf "%s\n" "BLOCKED: missing env$missing — see knowledge/integrations/ci-github.md." >&2; exit 69; }
command -v gh >/dev/null 2>&1 || { printf "%s\n" "BLOCKED: missing gh." >&2; exit 69; }
export GH_TOKEN
repo=$GITHUB_REPOSITORY

case "$1" in
  runs) exec gh run list -R "$repo" --limit 10 ;;
  view) exec gh run view "$2" -R "$repo" ;;
  view-log) exec gh run view "$2" -R "$repo" --log ;;
  rerun) exec gh run rerun "$2" -R "$repo" ;;
  dispatch) exec gh workflow run tests.yml -R "$repo" ;;
esac
