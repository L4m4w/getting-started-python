"""Verifiable upload/verify lifecycle for Allure TestOps executions.

Phases and outcomes are modelled explicitly:

- ``pending`` — nothing was written externally; no launch recorded.
- ``in_progress`` — an attempt is inside an external operation; the
  persisted ``phase`` (``launch_create`` or ``upload``) says which write
  may already have reached the server if the process dies here.
- ``sent`` — the upload command exited 0: the batch was delivered, but
  server-side processing of the expected result set is unconfirmed.
- ``failed`` — a proven refusal or a proven pre-write failure. A retry is
  allowed (operator-gated) and always reuses a recorded launch ID.
- ``unknown`` — indeterminate: timeout, interruption, an unreadable
  response after a possible write, or a non-zero batch exit where partial
  acceptance cannot be ruled out. Any further upload is blocked until
  verification or an explicit operator resolution.
- ``uploaded`` — terminal: the recorded launch ID, project and the full
  expected result set and bindings were confirmed on the server
  (automatically when the transport provides the evidence, or via an
  explicitly recorded manual confirmation).

Blind retries are impossible by construction: a recorded launch is never
replaced, an ordinary retry never creates a new launch, and every
indeterminate outcome blocks with diagnostics instead of re-sending.

The module is network-free: external calls go through an injected
transport object exposing create_launch / upload_package / get_launch /
list_launches / list_cases and optionally list_launch_results (None or
absent means "no per-result evidence available"). State persistence is an
injected callback so tests can capture every durable boundary.
"""
from dataclasses import dataclass, field, replace
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import uuid

from . import client, state as state_mod

PHASE_LAUNCH_CREATE = "launch_create"
PHASE_UPLOAD = "upload"

OUTCOME_BLOCKED = "blocked"
OUTCOME_SENT = "sent"
OUTCOME_FAILED = "failed"
OUTCOME_UNKNOWN = "unknown"
OUTCOME_INTERRUPTED = "interrupted"
OUTCOME_CONFIRMED = "confirmed"

VERDICT_CONFIRMED = "confirmed"
VERDICT_PARTIAL = "partial"
VERDICT_EMPTY = "empty"
VERDICT_CONTRADICTION = "contradiction"
VERDICT_INCONCLUSIVE = "inconclusive"
VERDICT_MISSING = "missing"
VERDICT_UNREACHABLE = "unreachable"


class LockHeldError(Exception):
    """The execution is already owned by another (possibly dead) process."""


class ExecutionLock:
    """Per-execution mutex covering load -> decision -> external op -> save.

    The lock file lives next to state.json. A second holder gets a clear
    refusal. A lock whose owner PID is dead is reclaimed as a mutex only —
    it never grants permission to bypass a persisted in_progress/unknown
    status, which is enforced by the state machine on the next load.
    """

    LOCK_NAME = "execution.lock"

    def __init__(self, state_dir, operation="external"):
        self.state_dir = Path(state_dir)
        self.operation = operation
        self.path = self.state_dir / self.LOCK_NAME
        self.token = uuid.uuid4().hex
        self._held = False

    @contextmanager
    def _gate(self):
        # Serialize stale-file reclamation: two contenders must not unlink
        # the replacement lock installed by the first contender.
        self.state_dir.mkdir(parents=True, exist_ok=True)
        with (self.state_dir / "execution.lock-gate").open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def acquire(self):
        with self._gate():
            return self._acquire_guarded()

    def _acquire_guarded(self):
        for _attempt in range(3):
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                self._reclaim_stale()
                continue
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"pid": os.getpid(), "token": self.token,
                           "operation": self.operation,
                           "acquired_at": state_mod._utc_now()}, handle)
            self._held = True
            return self
        raise LockHeldError(f"cannot acquire lock {self.path}")

    def _reclaim_stale(self):
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise LockHeldError(
                f"lock file unreadable or corrupt: {self.path}; inspect it "
                "and remove manually once no upload is running")
        if not isinstance(payload, dict):
            raise LockHeldError("lock file is not an object; inspect manually")
        pid = payload.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            raise LockHeldError(
                f"lock file {self.path} has no valid owner pid; remove it "
                "manually once no upload is running")
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            try:
                self.path.unlink()
            except FileNotFoundError:
                pass
            return
        except PermissionError:
            pass
        raise LockHeldError(
            f"execution is locked by pid {pid} "
            f"({payload.get('operation')}, since "
            f"{payload.get('acquired_at')})")

    def release(self):
        if not self._held:
            return
        self._held = False
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if payload.get("token") == self.token:
            try:
                self.path.unlink()
            except OSError:
                pass

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False


@dataclass
class ExternalCall:
    """Record of one transport interaction for the caller's upload log."""
    operation: str
    result: object = None
    error: str = None


@dataclass
class UploadRun:
    outcome: str
    status: str = None
    exit_code: int = None
    launch_id: int = None
    message: str = ""
    state: dict = None
    calls: list = field(default_factory=list)


@dataclass
class VerifyRun:
    verdict: str
    confirmed: bool
    status: str = None
    launch_id: int = None
    message: str = ""
    checks: dict = field(default_factory=dict)
    state: dict = None
    calls: list = field(default_factory=list)


def decide_upload(state, retry=False):
    """(allowed, reason, launch_id): the retry never invents a new launch."""
    upload = state.get("upload") or {}
    status = upload.get("status")
    launch_id = (state.get("launch") or {}).get("id")
    if status == "uploaded":
        return False, ("upload already confirmed for this execution; "
                       "it is never re-sent"), launch_id
    if status == "sent":
        return False, ("batch already delivered; run verify to confirm the "
                       "server-side result set before any re-send"), launch_id
    if status == "unknown":
        return False, ("previous outcome is indeterminate (possible partial "
                       "server-side write); verify or resolve manually "
                       "before any retry"), launch_id
    if status == "in_progress":
        return False, ("an attempt is recorded as in_progress; if the "
                       "process died, resolve it explicitly via "
                       "resolve_in_progress"), launch_id
    if status == "failed":
        if not upload.get("attempts"):
            return False, "upload marked failed without attempts", launch_id
        if not retry:
            return False, ("previous attempt failed; pass retry explicitly "
                           "after reviewing the cause"), launch_id
        return True, None, launch_id
    if status == "pending":
        if state.get("package") is None:
            return False, "no upload package built yet", launch_id
        return True, None, launch_id
    return False, f"unrecognized upload status: {status!r}", launch_id


def _classify_error(result, phase):
    """Proven-failure vs indeterminate classification of a transport error."""
    if result.error != "launch_error":
        return ("unknown", f"{phase} outcome is uncertain ({result.error}); the server may have "
                           "accepted part of the request")
    return ("failed", f"{phase} could not start ({result.error}); "
                      "no external write was possible")


def _run_call(calls, operation, thunk):
    """Execute a transport call; KeyboardInterrupt surfaces as an error."""
    try:
        result = thunk()
    except KeyboardInterrupt:
        calls.append(ExternalCall(operation, None, "interrupted"))
        raise
    calls.append(ExternalCall(operation, result,
                              getattr(result, "error", None)))
    return result


def _finish(state, persist, status, exit_code, detail, calls):
    state_mod.complete_attempt(state, status, exit_code, detail=detail)
    persist(state)
    return UploadRun(status if status != "sent" else OUTCOME_SENT,
                     status, exit_code,
                     (state.get("launch") or {}).get("id"),
                     detail or status, state, calls)


def perform_upload(state_dir, transport, *, launch_name, timeout_s=None,
                   retry=False, persist=None, lock=None):
    """One upload attempt under the execution lock.

    persist(state) is invoked at every durable boundary: the in_progress
    marker and the recorded launch reach disk BEFORE the external call
    that could make them true, so a crash never loses them. `transport`
    must provide create_launch(endpoint, project_id, name) and
    upload_package(endpoint, project_id, launch_id, package_dir,
    timeout_s), each returning a client.CommandResult.
    """
    state_dir = Path(state_dir)
    persist = persist or (lambda s: state_mod.save_state(state_dir, s))
    lock = lock or ExecutionLock(state_dir, operation="upload")
    calls = []
    with lock:
        state = state_mod.load_state(state_dir)
        if state is None:
            return UploadRun(OUTCOME_BLOCKED,
                             message=f"no state in {state_dir}; run plan first",
                             calls=calls)
        allowed, reason, launch_id = decide_upload(state, retry)
        if not allowed:
            return UploadRun(OUTCOME_BLOCKED,
                             status=state["upload"].get("status"),
                             launch_id=launch_id, message=reason,
                             state=state, calls=calls)
        package = state.get("package") or {}
        package_dir = Path(package.get("dir") or "")
        if not package_dir.is_dir():
            return UploadRun(OUTCOME_BLOCKED, status=state["upload"]["status"],
                             launch_id=launch_id,
                             message="package directory missing; rebuild it",
                             state=state, calls=calls)
        state_mod.begin_upload_attempt(state, package.get("sha256"))
        persist(state)

        if launch_id is None:
            state_mod.set_attempt_phase(state, PHASE_LAUNCH_CREATE)
            persist(state)
            try:
                created = _run_call(
                    calls, "launch_create",
                    lambda: transport.create_launch(
                        state["endpoint"], state["project_id"], launch_name))
            except KeyboardInterrupt:
                run = _finish(
                    state, persist, "unknown", None,
                    "interrupted during launch create; a launch may exist "
                    "server-side without a recorded ID", calls)
                return replace(run, outcome=OUTCOME_INTERRUPTED)
            if created.error:
                status, detail = _classify_error(created, PHASE_LAUNCH_CREATE)
                return _finish(state, persist, status, created.code,
                               detail, calls)
            if created.code != 0:
                return _finish(
                    state, persist, "unknown", created.code,
                    "launch create exited nonzero; a server-side write cannot "
                    "be ruled out — inspect and adopt the existing launch", calls)
            launch_id = client.parse_launch_id(created.stdout)
            if launch_id is None:
                return _finish(
                    state, persist, "unknown", created.code,
                    "launch create exited 0 but its ID is unreadable; a "
                    "launch probably exists server-side — find it via "
                    "launch list / UI and adopt it instead of creating "
                    "another", calls)
            url = (f"{state['endpoint'].rstrip('/')}/launch/{launch_id}")
            state_mod.record_launch(state, launch_id, launch_name, url)
            persist(state)

        state_mod.set_attempt_phase(state, PHASE_UPLOAD)
        persist(state)
        try:
            outcome = _run_call(
                calls, "upload",
                lambda: transport.upload_package(
                    state["endpoint"], state["project_id"], launch_id,
                    package_dir, timeout_s))
        except KeyboardInterrupt:
            run = _finish(
                state, persist, "unknown", None,
                "interrupted during batch upload; the launch may contain "
                "a partial result set", calls)
            return replace(run, outcome=OUTCOME_INTERRUPTED)
        if outcome.error:
            status, detail = _classify_error(outcome, PHASE_UPLOAD)
            return _finish(state, persist, status, outcome.code,
                           detail, calls)
        if outcome.code != 0:
            return _finish(
                state, persist, "unknown", outcome.code,
                f"batch upload exited {outcome.code}; the server may have "
                "accepted part of the batch — verify the launch before "
                "any retry, it is NOT safe to resend blindly", calls)
        return _finish(
            state, persist, "sent", 0,
            "batch delivered (exit 0); server-side processing of the "
            "expected result set is unconfirmed — run verify", calls)


def _compare_stats(observed, expected):
    """empty/match/partial/overdelivered/inconclusive for result counts."""
    if observed is None:
        return "inconclusive", {}
    expected = dict(expected or {})
    total_obs = sum(observed.values())
    total_exp = sum(expected.values())
    detail = {"observed": observed, "expected": expected}
    if total_obs == 0:
        return "empty", detail
    over = {key: value for key, value in observed.items()
            if value > expected.get(key, 0)}
    if over or total_obs > total_exp:
        detail["excess"] = over
        return "overdelivered", detail
    covered = all(observed.get(key, 0) == value
                  for key, value in expected.items())
    if covered and total_obs == total_exp:
        return "match", detail
    return "partial", detail


def _compare_results(observed, expected, bind):
    """match/mismatch for the per-result probe observations."""
    if observed is None:
        return "inconclusive", {"reason": "no per-result read path "
                                "available from the transport"}
    matched, extras, problems = set(), [], []
    for item in observed:
        name = item.get("name") or ""
        scenario = next((sid for sid in expected
                         if name.startswith(f"{sid}:")
                         or name == sid), None)
        if scenario is None:
            extras.append(name)
            continue
        if scenario in matched:
            problems.append(f"duplicate result for {scenario}")
            continue
        want = expected[scenario]
        if item.get("status") != want.get("status"):
            problems.append(
                f"{scenario}: status {item.get('status')} != "
                f"{want.get('status')}")
        if bind and item.get("test_case_id") != want.get("testops_id"):
            problems.append(
                f"{scenario}: test_case_id {item.get('test_case_id')} != "
                f"{want.get('testops_id')}")
        if not bind and item.get("test_case_id") is None:
            problems.append(f"{scenario}: result not linked to a case")
        matched.add(scenario)
    missing = sorted(set(expected) - matched)
    detail = {"matched": sorted(matched), "missing": missing,
              "foreign": extras, "problems": problems}
    if missing or extras or problems:
        return "mismatch", detail
    return "match", detail


def perform_verify(state_dir, transport, *, launch_id=None, persist=None,
                   lock=None):
    """Read-only verification of the recorded launch and result set.

    Confirms uploaded ONLY when every layer is proven server-side:
    recorded launch ID, project membership, the full expected per-status
    result counts, and the expected per-scenario bindings. Any layer that
    cannot be proven leaves the outcome undetermined — the report tells
    the operator exactly what still needs a manual check.
    """
    state_dir = Path(state_dir)
    persist = persist or (lambda s: state_mod.save_state(state_dir, s))
    lock = lock or ExecutionLock(state_dir, operation="verify")
    calls = []
    with lock:
        state = state_mod.load_state(state_dir)
        if state is None:
            return VerifyRun(VERDICT_INCONCLUSIVE, False,
                             message=f"no state in {state_dir}",
                             calls=calls)
        upload = state["upload"]
        recorded = state.get("launch") or {}
        lid = launch_id or recorded.get("id")
        if lid is None:
            return VerifyRun(VERDICT_INCONCLUSIVE, False,
                             status=upload.get("status"),
                             message="no launch ID recorded or passed",
                             state=state, calls=calls)
        if recorded.get("id") is not None and int(lid) != int(recorded["id"]):
            return VerifyRun(
                VERDICT_CONTRADICTION, False, status=upload.get("status"),
                launch_id=lid,
                message=(f"passed launch {lid} does not match recorded "
                         f"launch {recorded['id']}; refusing to confirm"),
                state=state, calls=calls)
        try:
            fetched = _run_call(
                calls, "launch_get",
                lambda: transport.get_launch(state["endpoint"], lid))
        except KeyboardInterrupt:
            return VerifyRun(VERDICT_UNREACHABLE, False,
                             status=upload.get("status"), launch_id=lid,
                             message="verify interrupted", state=state,
                             calls=calls)
        if fetched.error or fetched.code != 0:
            return VerifyRun(
                VERDICT_UNREACHABLE, False, status=upload.get("status"),
                launch_id=lid,
                message=(f"launch get failed "
                         f"({fetched.error or fetched.code}); state "
                         "unchanged"), state=state, calls=calls)
        entries = client.parse_launch(fetched.stdout)
        entry = next((item for item in entries
                      if item["id"] == int(lid)), None)
        if entry is None and not entries:
            return VerifyRun(
                VERDICT_INCONCLUSIVE, False, status=upload.get("status"),
                launch_id=lid,
                message="launch get returned an unreadable response; "
                        "state unchanged", state=state, calls=calls)
        if entry is None:
            checks = {"launch_found": False}
            state_mod.record_confirmation(
                state, VERDICT_MISSING, "transport",
                f"recorded launch {lid} not found in the response; it may "
                "be deleted — inspect in UI", checks)
            if upload.get("status") != "uploaded":
                upload["status"] = "unknown"
                upload["detail"] = (f"recorded launch {lid} missing on "
                                    "the server")
            persist(state)
            return VerifyRun(VERDICT_MISSING, False,
                             status=upload["status"],
                             launch_id=lid,
                             message="recorded launch not found server-side",
                             checks=checks, state=state, calls=calls)

        checks = {"launch_found": True,
                  "launch_id_match": entry["id"] == int(lid)}
        project_id = entry.get("project_id")
        if project_id is not None:
            checks["project_match"] = project_id == state["project_id"]
        else:
            checks["project_match"] = None
            listed = _project_membership(calls, transport, state, lid)
            checks["project_match"] = listed
        stats_verdict, stats_detail = _compare_stats(
            entry.get("stats"), state_mod.expected_stats(state))
        checks["result_set"] = stats_verdict
        checks["stats"] = stats_detail

        results_verdict, results_detail = _launch_results_check(
            calls, transport, state, lid)
        checks["bindings"] = results_verdict
        checks["bindings_detail"] = results_detail

        verdict = _verdict(checks)
        _apply_verdict(state, verdict, checks, lid)
        persist(state)
        confirmed = verdict == VERDICT_CONFIRMED
        return VerifyRun(verdict, confirmed, status=upload["status"],
                         launch_id=lid, message=_verdict_message(
                             verdict, checks, state),
                         checks=checks, state=state, calls=calls)


def _project_membership(calls, transport, state, launch_id):
    """True/False/None via `launch list --project-id P -q 'id = N'`."""
    lister = getattr(transport, "list_launches", None)
    if lister is None:
        return None
    try:
        outcome = _run_call(
            calls, "launch_list",
            lambda: lister(state["endpoint"], state["project_id"],
                           f"id = {launch_id}"))
    except KeyboardInterrupt:
        raise
    if outcome.error or outcome.code != 0:
        return None
    return any(item["id"] == int(launch_id)
               for item in client.parse_launch(outcome.stdout))


def _launch_results_check(calls, transport, state, launch_id):
    """bindings verdict via an optional per-result probe."""
    probe = getattr(transport, "list_launch_results", None)
    if probe is None:
        return "inconclusive", {"reason": "transport exposes no per-result "
                                "read path (allurectl 2.24.0 has none)"}
    try:
        observed = _run_call(
            calls, "launch_results",
            lambda: probe(state["endpoint"], launch_id))
    except KeyboardInterrupt:
        raise
    if isinstance(observed, client.CommandResult):
        if observed.error or observed.code != 0:
            return "inconclusive", {"reason": "result listing request failed"}
        observed = client.parse_launch_results(observed.stdout)
    expected = state_mod.expected_scenarios(state)
    bind = any(entry.get("testops_id") is not None
               for entry in expected.values())
    return _compare_results(observed, expected, bind)


def _verdict(checks):
    if checks.get("launch_found") is False:
        return VERDICT_MISSING
    if checks.get("launch_id_match") is False:
        return VERDICT_CONTRADICTION
    if checks.get("project_match") is False:
        return VERDICT_CONTRADICTION
    result_set = checks.get("result_set")
    if result_set == "empty":
        return VERDICT_EMPTY
    if result_set in ("overdelivered",):
        return VERDICT_CONTRADICTION
    if result_set == "partial":
        return VERDICT_PARTIAL
    if result_set != "match":
        return VERDICT_INCONCLUSIVE
    bindings = checks.get("bindings")
    if bindings == "mismatch":
        return VERDICT_CONTRADICTION
    if bindings != "match":
        return VERDICT_INCONCLUSIVE
    if checks.get("project_match") is not True:
        return VERDICT_INCONCLUSIVE
    return VERDICT_CONFIRMED


def _apply_verdict(state, verdict, checks, launch_id):
    upload = state["upload"]
    method = "transport"
    if verdict == VERDICT_CONFIRMED:
        state_mod.mark_upload_confirmed(
            state, method,
            "launch ID, project, full expected result set and bindings "
            "confirmed server-side", checks)
        return
    state_mod.record_confirmation(
        state, verdict, method, _verdict_message(verdict, checks, state),
        checks)
    if upload.get("status") in ("uploaded", "in_progress"):
        return
    if verdict == VERDICT_EMPTY:
        upload["detail"] = (
            f"launch {launch_id} currently has zero statistics; processing "
            "may still be pending — re-send remains blocked")
    elif verdict in (VERDICT_MISSING, VERDICT_CONTRADICTION):
        upload["status"] = "unknown"
        upload["detail"] = _verdict_message(verdict, checks, state)


def _verdict_message(verdict, checks, state):
    if verdict == VERDICT_CONFIRMED:
        return "launch, project, result set and bindings all confirmed"
    if verdict == VERDICT_EMPTY:
        return ("launch currently reports zero results; processing may still "
                "be pending — this does not authorize a retry")
    if verdict == VERDICT_MISSING:
        return "recorded launch not found on the server"
    if verdict == VERDICT_CONTRADICTION:
        detail = checks.get("stats") or {}
        return ("server observation contradicts the expectation "
                f"(project_match={checks.get('project_match')}, "
                f"result_set={checks.get('result_set')}, "
                f"bindings={checks.get('bindings')}, "
                f"excess={detail.get('excess')}); manual resolution required")
    if verdict == VERDICT_PARTIAL:
        return ("launch contains only part of the expected result set; "
                "check whether server processing finished and resolve "
                "manually — blind re-send risks duplicates")
    if verdict == VERDICT_UNREACHABLE:
        return "server could not be queried; state unchanged"
    return ("evidence inconclusive: launch is confirmed but the result "
            "set or bindings could not be proven automatically; inspect "
            "the launch in the UI and record a manual confirmation")
