#!/bin/sh
set -eu
cd "$(CDPATH= cd "$(dirname "$0")/.." && pwd)"
usage() { echo 'Usage: sh tools/run-tests.sh list | --allow-sut one CASE | --allow-sut group auth|registration|logout | --allow-sut all' >&2; exit 64; }
allow_sut=false
if [ "${1-}" = '--allow-sut' ]; then allow_sut=true; shift; fi
case "${1-}" in
list)
  [ "$#" -eq 1 ] || usage
  printf '%s\n' 'login-success [auth] tests/auth/test_login.py::TestLogin::test_success_login'
  printf '%s\n' 'login-enter [auth] tests/auth/test_login.py::TestLogin::test_success_login_with_press_enter'
  printf '%s\n' 'login-wrong-password [auth] tests/auth/test_login.py::TestLogin::test_wrong_credentials'
  printf '%s\n' 'register [registration] tests/registration/test_registration.py::TestRegistration::test_successful_registration'
  printf '%s\n' 'register-mismatch [registration] tests/registration/test_registration.py::TestRegistration::test_registration_with_mismatched_passwords'
  printf '%s\n' 'register-existing [registration] tests/registration/test_registration.py::TestRegistration::test_registration_with_existing_username'
  printf '%s\n' 'logout [logout] tests/logout/test_logout.py::TestLogout::test_logout'
  printf '%s\n' 'login-unknown-user [auth] tests/auth/test_login.py::TestLogin::test_login_with_unknown_username'
  printf '%s\n' 'login-retry-success [auth] tests/auth/test_login.py::TestLogin::test_success_login_after_wrong_password'
  exit 0 ;;
one|group) [ "$#" -eq 2 ] || usage ;;
all) [ "$#" -eq 1 ] || usage ;;
*) usage ;;
esac
case "$1:${2-}" in
  one:login-success) scope='tests/auth/test_login.py::TestLogin::test_success_login' ;;
  one:login-enter) scope='tests/auth/test_login.py::TestLogin::test_success_login_with_press_enter' ;;
  one:login-wrong-password) scope='tests/auth/test_login.py::TestLogin::test_wrong_credentials' ;;
  one:register) scope='tests/registration/test_registration.py::TestRegistration::test_successful_registration' ;;
  one:register-mismatch) scope='tests/registration/test_registration.py::TestRegistration::test_registration_with_mismatched_passwords' ;;
  one:register-existing) scope='tests/registration/test_registration.py::TestRegistration::test_registration_with_existing_username' ;;
  one:logout) scope='tests/logout/test_logout.py::TestLogout::test_logout' ;;
  one:login-unknown-user) scope='tests/auth/test_login.py::TestLogin::test_login_with_unknown_username' ;;
  one:login-retry-success) scope='tests/auth/test_login.py::TestLogin::test_success_login_after_wrong_password' ;;
  group:auth) scope='tests/auth' ;;
  group:registration) scope='tests/registration' ;;
  group:logout) scope='tests/logout' ;;
  all:) scope='tests' ;;
  *) usage ;;
esac
[ "$allow_sut" = true ] || { echo 'UI run requires authorized target/scope and --allow-sut acknowledgement.' >&2; exit 77; }
runner=${PYTHON:-python3}
printf 'Running: %s -m pytest -v --alluredir=allure-results %s\n' "$runner" "$scope"
exec "$runner" -m pytest -v --alluredir=allure-results "$scope"
