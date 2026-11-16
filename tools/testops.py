"""Plan, bind and (explicitly) upload CAT-UPD-VAL results to Allure TestOps.

Default behaviour is offline: plan/status/assign/package only read results and
write local state under artifacts/testops/<execution>/. Network access requires
--online for read-only queries (resolve/verify) or --execute for the entity
writing upload; both read ALLURE_TOKEN from the environment and never print it.
"""
import argparse
from contextlib import nullcontext
from functools import wraps
from dotenv import load_dotenv
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infrastructure.reporting.testops import (
    client, lifecycle, rest, results, state as state_mod, verification)
from test_data.consts.category_update import (
    INVALID_IDS, INVALID_NAMES, VALID_IDS, VALID_NAMES)

STATE_PARENT = ROOT / "artifacts" / "testops"
DEFAULT_ENDPOINT = "https://allure.qa.guru"
DEFAULT_PROJECT_ID = 5444
AQL_SCENARIO_SEARCH = 'name ~= "CAT-UPD-VAL"'
UPLOAD_MODES = ("bind", "isolate")
EXECUTION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
EXIT_BLOCKED = 69
EXIT_UNKNOWN = 75
EXIT_LAUNCH_ERROR = 127
EXIT_INTERRUPTED = 130


def load_environment():
    """Load only the project .env; exported values take precedence."""
    load_dotenv(ROOT / ".env", override=False)


def _guard(operation):
    """Serialize every state user and surface integrity failures as blocks."""
    @wraps(operation)
    def guarded(options, parser):
        try:
            execution = _execution_id(options, parser)
            with lifecycle.ExecutionLock(_state_dir(execution), operation.__name__):
                return operation(options, parser)
        except (results.ResultsIntegrityError, state_mod.StateCorruptError,
                lifecycle.LockHeldError, ValueError) as error:
            print(f"BLOCKED: {error}", file=sys.stderr)
            return EXIT_BLOCKED
    return guarded


def _assignments(state, mode):
    return {entry["uuid"]: (sid, entry.get("testops_id") if mode == "bind" else None)
            for sid, entry in state["scenarios"].items()}


def _validate_upload_package(state):
    package = state.get("package") or {}
    source = state.get("results") or {}
    if not package.get("input_sha256") or not package.get("assignments_sha256"):
        raise results.ResultsIntegrityError("legacy/unverified package; rebuild it")
    if state.get("unmapped") or not state.get("scenarios"):
        raise results.ResultsIntegrityError("execution is not fully mapped")
    if package.get("mode") == "bind" and state_mod.unresolved_ids(state):
        raise results.ResultsIntegrityError("bindings unresolved; rebuild after resolution")
    results.verify_source_digest(Path(source["path"]), package["input_sha256"])
    if source.get("sha256") != package["input_sha256"]:
        raise results.ResultsIntegrityError("plan changed after package; rebuild it")
    assignments = _assignments(state, package["mode"])
    if results.assignments_digest(assignments) != package["assignments_sha256"]:
        raise results.ResultsIntegrityError("bindings changed after package; rebuild it")
    scanned = results.scan_assignments(Path(source["path"]), _scenario_index())
    if scanned != {uid: sid for uid, (sid, _) in assignments.items()}:
        raise results.ResultsIntegrityError("mapping changed after package; re-plan")
    results.verify_package(Path(package["dir"]), package["sha256"])


class AllurectlTransport:
    """Thin adapter; no unsupported per-result read API is assumed."""
    def __init__(self, binary):
        self.binary = binary

    def _run(self, args, timeout=client.DEFAULT_TIMEOUT_S):
        return client.run(self.binary, args, token=_token(), timeout=timeout)

    def create_launch(self, endpoint, project_id, name):
        return self._run(client.launch_create_args(endpoint, project_id, name))

    def upload_package(self, endpoint, project_id, launch_id, directory, timeout):
        return self._run(client.upload_args(endpoint, project_id, launch_id, directory), timeout)

    def get_launch(self, endpoint, launch_id):
        return self._run(client.launch_get_args(endpoint, launch_id))

    def list_launches(self, endpoint, project_id, aql):
        return self._run(client.launch_list_args(endpoint, project_id, aql))


def _write_calls(state_dir, calls):
    # Raw tool responses may contain credentials; retain operational metadata only.
    if not calls:
        return
    with (state_dir / "upload.log").open("a", encoding="utf-8") as handle:
        for call in calls:
            handle.write(f"utc={state_mod._utc_now()} operation={call.operation} "
                         f"exit={getattr(call.result, 'code', None)} error={call.error}\n")


def _scenario_index():
    """Single source of truth: scenario IDs and values from the API contract."""
    index = {}
    base = "tests.api.test_category_update"
    for scenario_id, value in zip(INVALID_IDS, INVALID_NAMES):
        index[scenario_id] = {
            "full_name": f"{base}#test_update_category_rejects_invalid_name",
            "param": "name", "value": value}
    for scenario_id, value in zip(VALID_IDS, VALID_NAMES):
        index[scenario_id] = {
            "full_name": f"{base}#test_update_category_accepts_name_at_length_boundary",
            "param": "name", "value": value}
    return index


def _execution_id(options, parser):
    execution = options.execution
    if execution is None and options.results:
        path = Path(options.results).resolve()
        name = path.parent.name if path.name == "allure-results" else path.name
        if name:
            execution = name
    if execution is None:
        parser.error("pass --execution (or --results inside a run directory)")
    if not EXECUTION_PATTERN.fullmatch(execution):
        parser.error("execution must be a safe directory name "
                     "(letters, digits, _.-)")
    return execution


def _state_dir(execution_id):
    return STATE_PARENT / execution_id


def _token():
    """ALLURE_TOKEN from env only; its value is never printed or stored."""
    return os.environ.get("ALLURE_TOKEN") or None


def _endpoint(options):
    return options.endpoint or os.environ.get("ALLURE_ENDPOINT") or DEFAULT_ENDPOINT


def _project_id(options):
    if options.project_id is not None:
        return options.project_id
    env = os.environ.get("ALLURE_PROJECT_ID")
    if env and env.isdigit():
        return int(env)
    return DEFAULT_PROJECT_ID


def _require_network(binary, token):
    if binary is None:
        print("BLOCKED: allurectl not found; install it or set ALLURECTL.",
              file=sys.stderr)
        return EXIT_BLOCKED
    if not token:
        print("BLOCKED: ALLURE_TOKEN is not set in the environment.",
              file=sys.stderr)
        return EXIT_BLOCKED
    return None


def _load_or_new(options, execution_id):
    state_dir = _state_dir(execution_id)
    loaded = state_mod.load_state(state_dir)
    if loaded is not None:
        return loaded, state_dir
    return (state_mod.new_state(execution_id, _endpoint(options),
                                _project_id(options)), state_dir)


def _print_plan(state):
    print(f"Execution: {state['execution_id']}  "
          f"endpoint={state['endpoint']} project={state['project_id']}")
    res = state.get("results") or {}
    print(f"Results: {res.get('path')} files={res.get('files')} "
          f"sha256={res.get('sha256')}")
    for scenario_id, entry in (state.get("scenarios") or {}).items():
        print(f"  {scenario_id}: status={entry.get('status')} "
              f"binding={entry.get('binding')} "
              f"testops_id={entry.get('testops_id')}")
    if state.get("unmapped"):
        print(f"  UNMAPPED results: {len(state['unmapped'])}")
    print(f"Package: {state.get('package')}")
    print(f"Launch: {state.get('launch')}")
    print(f"Upload: {state.get('upload')}")


@_guard
def cmd_plan(options, parser):
    results_dir = Path(options.results).resolve()
    if not results_dir.is_dir():
        print(f"BLOCKED: results directory not found: {results_dir}",
              file=sys.stderr)
        return EXIT_BLOCKED
    execution_id = _execution_id(options, parser)
    loaded = results.load_results(results_dir)
    mapped, unmapped = results.map_scenarios(loaded, _scenario_index())
    state, state_dir = _load_or_new(options, execution_id)
    if (state["upload"].get("attempts") or state.get("launch")) and (
            (state.get("results") or {}).get("sha256") != results.results_digest(results_dir)):
        raise results.ResultsIntegrityError("cannot replace inputs after an upload attempt; use a new execution")
    state_mod.record_results(
        state, results_dir, results.results_digest(results_dir),
        len([p for p in results_dir.iterdir() if p.is_file()]), mapped, unmapped)
    state_mod.save_state(state_dir, state)
    _print_plan(state)
    if unmapped:
        print(f"WARNING: {len(unmapped)} results do not match any scenario "
              "signature and would be excluded from an upload package.")
    return 0


def _require_state(options, parser):
    execution_id = _execution_id(options, parser)
    state = state_mod.load_state(_state_dir(execution_id))
    if state is None:
        parser.error(f"no state for execution {execution_id}; run plan first")
    return state, _state_dir(execution_id)


@_guard
def cmd_status(options, parser):
    state, _ = _require_state(options, parser)
    _print_plan(state)
    return 0


@_guard
def cmd_assign(options, parser):
    state, state_dir = _require_state(options, parser)
    for pair in options.bindings:
        scenario_id, sep, raw_id = pair.partition("=")
        if not sep or not raw_id.isdigit():
            parser.error("assign expects SCENARIO=NUMERIC_TESTOPS_ID pairs")
        try:
            state_mod.set_binding(state, scenario_id, int(raw_id), "assign")
        except ValueError as error:
            print(f"BLOCKED: {error}", file=sys.stderr)
            return EXIT_BLOCKED
    state_mod.save_state(state_dir, state)
    _print_plan(state)
    return 0


@_guard
def cmd_resolve(options, parser):
    if not options.online:
        print("BLOCKED: resolve performs a read-only network request; "
              "rerun with --online.", file=sys.stderr)
        return EXIT_BLOCKED
    state, state_dir = _require_state(options, parser)
    binary = client.locate(options.allurectl)
    blocked = _require_network(binary, _token())
    if blocked is not None:
        return blocked
    args = client.case_list_args(state["endpoint"], state["project_id"],
                                 AQL_SCENARIO_SEARCH)
    print("+ " + client.describe(args), flush=True)
    outcome = client.run(binary, args)
    if outcome.error or outcome.code != 0:
        print(f"Resolve failed: {outcome.error or outcome.code} "
              "(tool output withheld)", file=sys.stderr)
        return outcome.code or EXIT_LAUNCH_ERROR
    found = client.parse_cases(outcome.stdout)
    print(f"Found {len(found)} cases matching {AQL_SCENARIO_SEARCH!r}")
    for scenario_id, entry in sorted(state["scenarios"].items()):
        if entry.get("binding") == "bound" and entry.get("testops_id") is not None:
            print(f"  {scenario_id}: already bound to {entry['testops_id']}")
            continue
        candidates = [case for case in found
                      if re.search(r"(?<![A-Za-z0-9_-])" + re.escape(scenario_id)
                                   + r"(?![A-Za-z0-9_-])", case["name"])]
        if len(candidates) > 1:
            state_mod.mark_ambiguous(state, scenario_id)
            print(f"  {scenario_id}: AMBIGUOUS {sorted(c['id'] for c in candidates)}")
            continue
        if not candidates:
            print(f"  {scenario_id}: unresolved (no case found)")
            continue
        try:
            state_mod.set_binding(state, scenario_id, candidates[0]["id"], "search")
            print(f"  {scenario_id}: bound to {candidates[0]['id']}")
        except ValueError as error:
            state_mod.mark_ambiguous(state, scenario_id)
            print(f"  {scenario_id}: AMBIGUOUS ({error})")
    state_mod.save_state(state_dir, state)
    missing = state_mod.unresolved_ids(state)
    if missing:
        print(f"Unresolved: {', '.join(missing)}", file=sys.stderr)
        return EXIT_BLOCKED
    return 0


@_guard
def cmd_package(options, parser):
    state, state_dir = _require_state(options, parser)
    scenarios = state.get("scenarios") or {}
    if state.get("unmapped"):
        print("BLOCKED: unmapped results present; package only from a fully "
              "mapped execution.", file=sys.stderr)
        return EXIT_BLOCKED
    if not scenarios:
        print("BLOCKED: no mapped scenarios; run plan first.", file=sys.stderr)
        return EXIT_BLOCKED
    if options.mode == "bind":
        missing = state_mod.unresolved_ids(state)
        if missing:
            print(f"BLOCKED: bind mode requires resolved TestOps IDs; "
                  f"missing: {', '.join(missing)}", file=sys.stderr)
            return EXIT_BLOCKED
    source_dir = Path((state.get("results") or {}).get("path") or "")
    if not source_dir.is_dir():
        print("BLOCKED: recorded results directory is missing.", file=sys.stderr)
        return EXIT_BLOCKED
    assignments = {}
    for scenario_id, entry in scenarios.items():
        case_id = entry.get("testops_id") if options.mode == "bind" else None
        if entry.get("uuid"):
            assignments[entry["uuid"]] = (scenario_id, case_id)
    destination = state_dir / "upload-results"
    if state["upload"].get("attempts") or state.get("launch"):
        raise results.ResultsIntegrityError("cannot rebuild a package after an upload attempt")
    expected_digest = (state.get("results") or {}).get("sha256")
    if not expected_digest:
        raise results.ResultsIntegrityError("plan has no input digest; re-plan")
    info = results.build_package_verified(
        source_dir, destination, expected_digest=expected_digest,
        assignments=assignments, index=_scenario_index())
    state_mod.record_package(state, destination, info, options.mode)
    state_mod.save_state(state_dir, state)
    print(f"Package built: {destination} files={info['files']} "
          f"results={info['results']} sha256={info['sha256']}")
    return 0


@_guard
def cmd_upload(options, parser):
    if not options.execute:
        print("BLOCKED: upload requires explicit --execute authorization.", file=sys.stderr)
        return EXIT_BLOCKED
    state, state_dir = _require_state(options, parser)
    allowed, reason, _ = lifecycle.decide_upload(state, options.retry)
    if not allowed:
        print(f"BLOCKED: {reason}", file=sys.stderr)
        return EXIT_BLOCKED
    binary = client.locate(options.allurectl)
    blocked = _require_network(binary, _token())
    if blocked is not None:
        return blocked
    _validate_upload_package(state)
    run = lifecycle.perform_upload(
        state_dir, AllurectlTransport(binary),
        launch_name=options.launch_name or f"CAT-UPD-VAL {state['execution_id']}",
        timeout_s=options.timeout, retry=options.retry, lock=nullcontext())
    _write_calls(state_dir, run.calls)
    print(f"Upload outcome={run.outcome} launch={run.launch_id}: {run.message}")
    if run.outcome == lifecycle.OUTCOME_SENT:
        return 0
    if run.outcome == lifecycle.OUTCOME_INTERRUPTED:
        return EXIT_INTERRUPTED
    if run.outcome == lifecycle.OUTCOME_UNKNOWN:
        return EXIT_UNKNOWN
    if run.outcome == lifecycle.OUTCOME_BLOCKED:
        return EXIT_BLOCKED
    return run.exit_code or EXIT_LAUNCH_ERROR


@_guard
def cmd_verify(options, parser):
    if not options.online:
        print("BLOCKED: verify requires --online.", file=sys.stderr)
        return EXIT_BLOCKED
    state, state_dir = _require_state(options, parser)
    transport = options.transport
    if transport not in ("allurectl", "rest"):
        raise ValueError("unsupported verification transport")
    binary = client.locate(options.allurectl) if transport == "allurectl" else None
    if not _token():
        print("BLOCKED: ALLURE_TOKEN is not set.", file=sys.stderr)
        return EXIT_BLOCKED
    if transport == "allurectl":
        blocked = _require_network(binary, _token())
        if blocked is not None:
            return blocked
    # Confirmation must concern the immutable package that was actually sent.
    _validate_upload_package(state)
    package_sha = state["package"]["sha256"]
    if state["upload"].get("package_sha256") != package_sha:
        raise results.ResultsIntegrityError("no matching recorded upload package")
    if not (state.get("launch") or {}).get("id"):
        raise ValueError("no recorded launch; adopt it explicitly before verification")
    if transport == "rest":
        run = verification.perform_snapshot_verify(
            state_dir, rest.RestProbe(_token()), launch_id=options.launch_id,
            lock=nullcontext())
    else:
        run = lifecycle.perform_verify(
            state_dir, AllurectlTransport(binary), launch_id=options.launch_id,
            lock=nullcontext())
    _write_calls(state_dir, run.calls)
    print(f"Verify verdict={run.verdict} launch={run.launch_id}: {run.message}")
    if run.confirmed:
        return 0
    if run.verdict in (lifecycle.VERDICT_MISSING, lifecycle.VERDICT_CONTRADICTION):
        return EXIT_BLOCKED
    return EXIT_UNKNOWN


def main():
    load_environment()
    os.chdir(ROOT)
    parser = argparse.ArgumentParser(description=__doc__)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--endpoint",
                        help="TestOps base URL (env ALLURE_ENDPOINT)")
    common.add_argument("--project-id", type=int,
                        help="TestOps project (env ALLURE_PROJECT_ID, default 5444)")
    common.add_argument("--allurectl", help="explicit path to allurectl")
    common.add_argument("--results", help="allure-results directory")
    common.add_argument("--execution", help="execution/state ID")
    actions = parser.add_subparsers(dest="action", required=True)

    actions.add_parser("plan", parents=[common],
                       help="scan results and write/refresh local plan")
    actions.add_parser("status", parents=[common], help="print stored state")
    assign = actions.add_parser("assign", parents=[common],
                              help="manually bind SCENARIO=ID pairs")
    assign.add_argument("bindings", nargs="+")
    resolve = actions.add_parser(
        "resolve", parents=[common],
        help="bind scenarios via read-only case search")
    resolve.add_argument("--online", action="store_true",
                         help="allow the read-only network request")
    package = actions.add_parser("package", parents=[common],
                                 help="build an upload package copy")
    package.add_argument("--mode", choices=UPLOAD_MODES, default="bind")
    upload = actions.add_parser(
        "upload", parents=[common],
        help="create launch and upload the built package")
    upload.add_argument("--execute", action="store_true",
                        help="perform the real entity-writing upload")
    upload.add_argument("--retry", action="store_true",
                        help="allow retry after a failed attempt")
    upload.add_argument("--launch-name")
    upload.add_argument("--timeout", type=int, default=client.UPLOAD_TIMEOUT_S)
    verify = actions.add_parser(
        "verify", parents=[common],
        help="confirm a recorded launch via read-only query")
    verify.add_argument("--online", action="store_true",
                        help="allow the read-only network request")
    verify.add_argument("--launch-id", type=int)
    verify.add_argument("--transport", choices=("allurectl", "rest"),
                        default="allurectl", help="explicit read-only verification transport")
    options = parser.parse_args()

    if options.action == "plan":
        if not options.results:
            parser.error("plan requires --results")
        return cmd_plan(options, parser)
    if options.action == "status":
        return cmd_status(options, parser)
    if options.action == "assign":
        return cmd_assign(options, parser)
    if options.action == "resolve":
        return cmd_resolve(options, parser)
    if options.action == "package":
        return cmd_package(options, parser)
    if options.action == "upload":
        return cmd_upload(options, parser)
    if options.action == "verify":
        return cmd_verify(options, parser)
    return 0


if __name__ == "__main__":
    sys.exit(main())
