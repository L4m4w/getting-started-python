"""Verify an upload against a normalized server-side launch snapshot.

The probe side (the wave-15 read-only REST client) exposes
``read_snapshot(endpoint, launch_id) -> dict``; this module owns the
verdict. ``evaluate_snapshot`` is a pure function: it re-validates the
snapshot contract and compares every layer against the expected result
set from the persisted state. ``perform_snapshot_verify`` wraps it with
the execution lock and state persistence for the CLI.

A malformed snapshot can never confirm: the contract is re-checked
before any comparison. ``confirmed`` requires all of these at once:

- outcome ``complete`` plus complete, self-consistent pagination;
- the recorded launch ID and the right project on the launch itself and
  on every result row;
- ``closed`` and ``ready`` — server-side processing has finished;
- a non-empty expected set covered by exactly one correctly named row
  per scenario — no foreign rows, no duplicated rows or result IDs;
- exact per-status statistics matching the expectation and consistent
  with the observed rows;
- exact statuses — ``in_progress``/``unknown`` mean the server is still
  processing, not a failure and not a success;
- the agreed case bindings. In isolate mode the found case IDs are kept
  as candidates, but nothing auto-confirms until bindings are assigned.

Evidence persisted into the state is deliberately distilled: booleans,
verdicts, counts, scenario IDs, case IDs and bounded problem strings —
never raw HTTP payloads, credentials or full result bodies.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from . import lifecycle, state as state_mod

VERDICT_CONFIRMED = lifecycle.VERDICT_CONFIRMED
VERDICT_PARTIAL = lifecycle.VERDICT_PARTIAL
VERDICT_EMPTY = lifecycle.VERDICT_EMPTY
VERDICT_CONTRADICTION = lifecycle.VERDICT_CONTRADICTION
VERDICT_INCONCLUSIVE = lifecycle.VERDICT_INCONCLUSIVE
VERDICT_MISSING = lifecycle.VERDICT_MISSING
VERDICT_UNREACHABLE = lifecycle.VERDICT_UNREACHABLE

SNAPSHOT_OUTCOMES = ("complete", "missing", "unreachable", "inconclusive")
IN_FLIGHT_STATUSES = ("in_progress", "unknown")
METHOD = "rest-snapshot"
_ITEM_LIMIT = 20
_TEXT_LIMIT = 200


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _clip(value, limit=_TEXT_LIMIT):
    text = "" if value is None else str(value)
    return text if len(text) <= limit else text[:limit] + "..."


def _cap(items, limit=_ITEM_LIMIT):
    return [_clip(item) for item in list(items)[:limit]]


def _counts_equal(first, second):
    """Per-status counters equal when missing keys mean zero."""
    keys = set(first) | set(second)
    return all(first.get(key, 0) == second.get(key, 0) for key in keys)


def _result_problems(index, item):
    if not isinstance(item, dict):
        return [f"results[{index}] is not an object"]
    required = ("id", "name", "status", "test_case_id", "launch_id",
                "project_id", "hidden", "retried_by_id")
    problems = [f"results[{index}].{key} is missing" for key in required
                if key not in item]
    if not _is_int(item.get("id")):
        problems.append(f"results[{index}].id is not an int")
    if not isinstance(item.get("name"), str):
        problems.append(f"results[{index}].name is not a str")
    if not isinstance(item.get("status"), str):
        problems.append(f"results[{index}].status is not a str")
    case_id = item.get("test_case_id")
    if case_id is not None and not _is_int(case_id):
        problems.append(f"results[{index}].test_case_id is not an int")
    if not _is_int(item.get("launch_id")):
        problems.append(f"results[{index}].launch_id is not an int")
    if not _is_int(item.get("project_id")):
        problems.append(f"results[{index}].project_id is not an int")
    if not isinstance(item.get("hidden"), bool):
        problems.append(f"results[{index}].hidden is not a bool")
    retried = item.get("retried_by_id")
    if retried is not None and not _is_int(retried):
        problems.append(f"results[{index}].retried_by_id is not an int")
    return problems


def _snapshot_problems(snapshot):
    """Contract violations; an empty list means the shape is valid.

    Payload fields (launch/ready/stats/results/pagination) are required
    only for ``outcome == "complete"`` — other outcomes may carry none.
    """
    if not isinstance(snapshot, dict):
        return ["snapshot is not an object"]
    outcome = snapshot.get("outcome")
    if outcome not in SNAPSHOT_OUTCOMES:
        return [f"outcome missing or unknown: {outcome!r}"]
    problems = []
    reason = snapshot.get("reason")
    if reason is not None and not isinstance(reason, str):
        problems.append("reason is not a str")
    if outcome != "complete":
        return problems
    for key in ("reason", "launch", "ready", "stats", "results", "pagination"):
        if key not in snapshot:
            problems.append(f"{key} is missing")
    launch = snapshot.get("launch")
    if not isinstance(launch, dict):
        problems.append("launch missing or not an object")
    else:
        if not _is_int(launch.get("id")):
            problems.append("launch.id is not an int")
        if not _is_int(launch.get("project_id")):
            problems.append("launch.project_id is not an int")
        if not isinstance(launch.get("closed"), bool):
            problems.append("launch.closed is not a bool")
    ready = snapshot.get("ready")
    if ready is not None and not isinstance(ready, bool):
        problems.append("ready is not a bool/None")
    stats = snapshot.get("stats")
    if stats is not None:
        if not isinstance(stats, dict):
            problems.append("stats is not an object")
        else:
            for key, value in stats.items():
                if not isinstance(key, str) or not _is_int(value) \
                        or value < 0:
                    problems.append(
                        f"stats[{key!r}] is not a nonnegative int")
    results = snapshot.get("results")
    if not isinstance(results, list):
        problems.append("results missing or not a list")
    else:
        for index, item in enumerate(results):
            problems.extend(_result_problems(index, item))
    pagination = snapshot.get("pagination")
    if not isinstance(pagination, dict):
        problems.append("pagination missing or not an object")
    else:
        if not isinstance(pagination.get("complete"), bool):
            problems.append("pagination.complete is not a bool")
        if not _is_int(pagination.get("pages")) \
                or pagination.get("pages", 0) < 0:
            problems.append("pagination.pages is not a nonnegative int")
        if "total_elements" not in pagination:
            problems.append("pagination.total_elements is missing")
        total = pagination.get("total_elements")
        if total is not None and (not _is_int(total) or total < 0):
            problems.append(
                "pagination.total_elements is not a nonnegative int")
    return problems


def _match_scenario(name, expected):
    """Exact scenario-ID boundary: '...-0010' never matches '...-001'.

    The colon after the ID makes the prefix check unambiguous, so a row
    can match at most one expected scenario no matter the order.
    """
    for scenario_id in expected:
        if name == scenario_id or name.startswith(f"{scenario_id}:"):
            return scenario_id
    return None


@dataclass
class Assessment:
    """Verdict of one snapshot; `checks` is distilled, persistence-safe."""
    verdict: str
    confirmed: bool
    checks: dict = field(default_factory=dict)
    detail: str = ""


def evaluate_snapshot(snapshot, expected, *, launch_id, project_id):
    """Pure verdict of a ``read_snapshot()`` dict against expectations.

    `expected` maps scenario_id -> {"status", "testops_id"} (see
    ``state_mod.expected_scenarios``). Never raises on malformed input:
    contract violations yield an inconclusive assessment, not an error.
    """
    problems = _snapshot_problems(snapshot)
    if problems:
        return Assessment(
            VERDICT_INCONCLUSIVE, False,
            {"contract": "malformed", "problems": _cap(problems)},
            "snapshot violates the probe contract: "
            + "; ".join(_cap(problems, 3)))
    outcome = snapshot["outcome"]
    checks = {"contract": "ok", "probe": outcome}
    reason = _clip(snapshot.get("reason"))
    if reason:
        checks["reason"] = reason
    if outcome != "complete":
        verdict = {"missing": VERDICT_MISSING,
                   "unreachable": VERDICT_UNREACHABLE}.get(
                       outcome, VERDICT_INCONCLUSIVE)
        checks["launch_found"] = False if outcome == "missing" else None
        return Assessment(
            verdict, False, checks,
            f"probe outcome: {outcome}"
            + (f" ({reason})" if reason else ""))

    expected = {sid: dict(entry) for sid, entry in (expected or {}).items()
                if isinstance(sid, str) and isinstance(entry, dict)}
    checks["expected_set"] = "ok" if expected else "empty"
    if not expected:
        return Assessment(VERDICT_INCONCLUSIVE, False, checks,
                          "the state holds no expected scenario set")

    launch = snapshot["launch"]
    results = snapshot["results"]
    pagination = snapshot["pagination"]
    stats = snapshot["stats"]
    ready = snapshot["ready"]
    lid = int(launch_id)
    contradictions, incomplete, anomalies = [], [], []

    checks["launch_found"] = True
    checks["launch_id_match"] = launch["id"] == lid
    if not checks["launch_id_match"]:
        contradictions.append(
            f"snapshot launch id {launch['id']} != recorded {lid}")
    checks["project_match"] = launch["project_id"] == project_id
    if not checks["project_match"]:
        contradictions.append(
            f"launch project {launch['project_id']} != {project_id}")
    checks["closed"] = launch["closed"]
    if launch["closed"] is not True:
        incomplete.append("launch is not closed")
    checks["ready"] = ready
    if ready is not True:
        incomplete.append(f"ready flag is {ready!r}")
    checks["pages"] = pagination["pages"]
    if not pagination["complete"]:
        checks["pagination"] = "incomplete"
        incomplete.append("pagination did not complete")
    else:
        checks["pagination"] = "complete"
    total = pagination.get("total_elements")
    if total is None or pagination["pages"] < 1:
        incomplete.append("pagination does not establish a complete page count/total")
    if total is not None and total != len(results):
        checks["pagination"] = "inconsistent"
        incomplete.append(
            f"pagination total {total} != {len(results)} observed rows")
    checks["rows_count"] = len(results)

    matched, candidates, seen_ids = set(), {}, set()
    foreign = 0
    for item in results:
        rid = item["id"]
        if rid in seen_ids:
            anomalies.append(f"duplicate result id {rid}")
        seen_ids.add(rid)
        if item["launch_id"] != lid:
            contradictions.append(
                f"result {rid}: launch_id {item['launch_id']} != {lid}")
        if item["project_id"] != project_id:
            contradictions.append(
                f"result {rid}: project_id {item['project_id']} "
                f"!= {project_id}")
        if item["hidden"]:
            anomalies.append(f"result {rid} is hidden")
        if item["retried_by_id"] is not None:
            anomalies.append(
                f"result {rid} superseded by {item['retried_by_id']}")
        scenario_id = _match_scenario(item["name"], expected)
        if scenario_id is None:
            foreign += 1
            continue
        if scenario_id in matched:
            anomalies.append(
                f"second row for {scenario_id} (result {rid}); the "
                "'latest' row is never picked silently")
            continue
        matched.add(scenario_id)
        want = expected[scenario_id]
        status = item["status"]
        if status in IN_FLIGHT_STATUSES:
            incomplete.append(
                f"{scenario_id}: status {status} — still processing")
        elif want.get("status") is None:
            incomplete.append(f"{scenario_id}: no expected status")
        elif status != want["status"]:
            contradictions.append(
                f"{scenario_id}: status {status} != expected "
                f"{want['status']}")
        case_id = item["test_case_id"]
        wanted = want.get("testops_id")
        if wanted is not None:
            if case_id != wanted:
                contradictions.append(
                    f"{scenario_id}: test_case_id {case_id} != bound "
                    f"{wanted}")
        else:
            candidates[scenario_id] = case_id
            if case_id is None:
                anomalies.append(
                    f"{scenario_id}: result is not linked to a case")

    missing = sorted(set(expected) - matched)
    checks["matched"] = sorted(matched)
    checks["missing"] = missing
    checks["foreign"] = foreign
    if foreign:
        contradictions.append(
            f"{foreign} row(s) match no expected scenario")
    if candidates:
        checks["candidates"] = dict(sorted(candidates.items()))

    expected_stats = {}
    for entry in expected.values():
        status = entry.get("status")
        if status:
            expected_stats[status] = expected_stats.get(status, 0) + 1
    rows_stats = {}
    for item in results:
        status = item["status"]
        rows_stats[status] = rows_stats.get(status, 0) + 1
    checks["stats_expected"] = expected_stats
    if stats is None:
        checks["result_set"] = "inconclusive"
        checks["stats_consistent"] = None
    else:
        checks["stats_observed"] = dict(sorted(stats.items()))
        checks["stats_consistent"] = _counts_equal(stats, rows_stats)
        if sum(stats.values()) == 0:
            checks["result_set"] = "empty" if not results else "partial"
        else:
            over = {key: value for key, value in stats.items()
                    if value > expected_stats.get(key, 0)}
            if over or sum(stats.values()) > sum(expected_stats.values()):
                checks["result_set"] = "overdelivered"
                contradictions.append(
                    f"statistics exceed the expected set: {over or stats}")
            elif all(stats.get(key, 0) == value
                     for key, value in expected_stats.items()) \
                    and sum(stats.values()) == sum(expected_stats.values()):
                checks["result_set"] = "match"
            else:
                checks["result_set"] = "partial"
        if not _counts_equal(stats, rows_stats) \
                and not anomalies and not incomplete:
            # A mismatch is a contradiction only without anomalies or
            # unfinished processing that could legitimately explain it.
            contradictions.append(
                f"statistics {stats} inconsistent with observed "
                f"rows {rows_stats}")

    checks["problems"] = _cap(contradictions)
    checks["anomalies"] = _cap(anomalies)
    checks["incomplete"] = _cap(incomplete)
    if contradictions:
        verdict = VERDICT_CONTRADICTION
    elif incomplete or anomalies or stats is None:
        verdict = VERDICT_INCONCLUSIVE
    elif checks["result_set"] == "empty":
        verdict = VERDICT_EMPTY
    elif missing or checks["result_set"] == "partial":
        verdict = VERDICT_PARTIAL
    elif not all(entry.get("testops_id") is not None
                 for entry in expected.values()):
        verdict = VERDICT_INCONCLUSIVE
    else:
        verdict = VERDICT_CONFIRMED
    detail = _detail(verdict, contradictions=contradictions,
                     incomplete=incomplete, anomalies=anomalies,
                     missing=missing, candidates=candidates,
                     stats=stats, checks=checks)
    return Assessment(verdict, verdict == VERDICT_CONFIRMED,
                      checks, detail)


def _detail(verdict, *, contradictions, incomplete, anomalies, missing,
            candidates, stats, checks):
    if verdict == VERDICT_CONFIRMED:
        return ("launch, project, full expected result set, statuses "
                "and case bindings confirmed server-side")
    if verdict == VERDICT_CONTRADICTION:
        return ("server evidence contradicts the expectation: "
                + "; ".join(_cap(contradictions, 3)))
    if verdict == VERDICT_EMPTY:
        return ("recorded launch currently reports no results; this observation "
                "does not authorize re-sending the batch")
    if verdict == VERDICT_PARTIAL:
        parts = []
        if missing:
            parts.append("missing " + ", ".join(missing))
        if checks.get("result_set") == "partial":
            parts.append("statistics cover only part of the expected set")
        return ("partial result set (" + "; ".join(parts) + "); re-send "
                "stays blocked — resolve manually")
    if verdict == VERDICT_INCONCLUSIVE:
        causes = _cap(incomplete) + _cap(anomalies)
        if stats is None and checks.get("result_set") == "inconclusive":
            causes.append("statistics are not readable")
        if candidates and not causes:
            causes.append("rows verified but case bindings are not "
                          "agreed; found case IDs recorded as candidates")
        if not causes:
            causes.append("a required evidence layer could not be proven")
        return "cannot confirm automatically: " + "; ".join(causes[:3])
    return verdict


def _apply_assessment(state, assessment):
    """Persist the verdict; only proven outcomes change the status.

    `confirmed` promotes to `uploaded`; an empty launch remains blocked
    because this observation does not prove that no batch was accepted;
    `missing`/`contradiction`/`partial` degrade to `unknown` so even an
    explicit retry stays blocked. `inconclusive`/`unreachable` record
    evidence without touching the status. Terminal `uploaded` and a live
    `in_progress` attempt are never rewritten here.
    """
    upload = state["upload"]
    if assessment.verdict == VERDICT_CONFIRMED:
        state_mod.mark_upload_confirmed(
            state, METHOD, assessment.detail, assessment.checks)
        return
    state_mod.record_confirmation(
        state, assessment.verdict, METHOD, assessment.detail,
        assessment.checks)
    if upload.get("status") not in ("sent", "unknown", "failed"):
        return
    if assessment.verdict in (VERDICT_EMPTY, VERDICT_MISSING,
                              VERDICT_CONTRADICTION, VERDICT_PARTIAL):
        upload["status"] = "unknown"
        upload["detail"] = assessment.detail


@contextmanager
def _held(lock):
    """Enter the lock unless the caller already holds it.

    An ExecutionLock with `_held` set is used without re-acquiring or
    releasing — ownership stays with the caller. Any other context
    manager (including contextlib.nullcontext) is entered normally.
    """
    if getattr(lock, "_held", False):
        yield lock
    else:
        with lock:
            yield lock


def perform_snapshot_verify(state_dir, probe, *, launch_id=None,
                            persist=None, lock=None):
    """Verify the recorded launch through a ``read_snapshot`` probe.

    The load -> probe -> verdict -> persist cycle runs under the
    execution lock; a coordinator that already holds the lock passes the
    same ExecutionLock (it is not re-acquired or released) or any other
    context manager. `probe` only needs ``read_snapshot(endpoint,
    launch_id)`` returning the normalized dict. Only a fully proven
    snapshot promotes the state to ``uploaded``.
    """
    state_dir = Path(state_dir)
    persist = persist or (lambda s: state_mod.save_state(state_dir, s))
    if lock is None:
        lock = lifecycle.ExecutionLock(state_dir, operation="verify")
    calls = []
    with _held(lock):
        state = state_mod.load_state(state_dir)
        if state is None:
            return lifecycle.VerifyRun(
                VERDICT_INCONCLUSIVE, False,
                message=f"no state in {state_dir}", calls=calls)
        upload = state["upload"]
        status = upload.get("status")
        recorded = state.get("launch") or {}
        if status == "uploaded":
            return lifecycle.VerifyRun(
                VERDICT_CONFIRMED, True, status=status,
                launch_id=recorded.get("id"),
                message="upload already confirmed; terminal state",
                state=state, calls=calls)
        if status == "in_progress":
            return lifecycle.VerifyRun(
                VERDICT_INCONCLUSIVE, False, status=status,
                launch_id=recorded.get("id"),
                message="an upload attempt is recorded in_progress; "
                        "resolve it explicitly before verification",
                state=state, calls=calls)
        lid = launch_id if launch_id is not None else recorded.get("id")
        if recorded.get("id") is None or lid is None:
            return lifecycle.VerifyRun(
                VERDICT_INCONCLUSIVE, False, status=status,
                message="no launch ID recorded or passed",
                state=state, calls=calls)
        try:
            lid = int(lid)
        except (TypeError, ValueError):
            return lifecycle.VerifyRun(
                VERDICT_INCONCLUSIVE, False, status=status,
                message=f"launch ID is not numeric: {_clip(lid)!r}",
                state=state, calls=calls)
        if recorded.get("id") is not None and lid != int(recorded["id"]):
            assessment = Assessment(
                VERDICT_CONTRADICTION, False,
                {"contract": "ok", "probe": None, "launch_found": None,
                 "launch_id_match": False},
                f"passed launch {lid} does not match recorded launch "
                f"{recorded['id']}; refusing to confirm")
            _apply_assessment(state, assessment)
            persist(state)
            return lifecycle.VerifyRun(
                assessment.verdict, assessment.confirmed,
                status=upload["status"], launch_id=lid,
                message=assessment.detail, checks=assessment.checks,
                state=state, calls=calls)
        expected = state_mod.expected_scenarios(state)
        if not expected:
            return lifecycle.VerifyRun(
                VERDICT_INCONCLUSIVE, False, status=status, launch_id=lid,
                message="the state holds no expected scenario set",
                state=state, calls=calls)
        reader = getattr(probe, "read_snapshot", None)
        if reader is None:
            return lifecycle.VerifyRun(
                VERDICT_INCONCLUSIVE, False, status=status, launch_id=lid,
                message="probe exposes no read_snapshot path; the "
                        "server-side result set cannot be proven",
                state=state, calls=calls)
        try:
            snapshot = reader(state["endpoint"], lid)
        except KeyboardInterrupt:
            calls.append(lifecycle.ExternalCall(
                "read_snapshot", None, "interrupted"))
            return lifecycle.VerifyRun(
                VERDICT_UNREACHABLE, False, status=status, launch_id=lid,
                message="verify interrupted", state=state, calls=calls)
        except Exception as error:
            calls.append(lifecycle.ExternalCall(
                "read_snapshot", None, type(error).__name__))
            return lifecycle.VerifyRun(
                VERDICT_UNREACHABLE, False, status=status, launch_id=lid,
                message=f"probe raised {type(error).__name__}; "
                        "state unchanged", state=state, calls=calls)
        # Only the distilled outcome is recorded — the raw snapshot never
        # reaches the caller's log or the persisted state.
        calls.append(lifecycle.ExternalCall(
            "read_snapshot",
            snapshot.get("outcome") if isinstance(snapshot, dict)
            else type(snapshot).__name__))
        assessment = evaluate_snapshot(
            snapshot, expected, launch_id=lid,
            project_id=state["project_id"])
        _apply_assessment(state, assessment)
        persist(state)
        return lifecycle.VerifyRun(
            assessment.verdict, assessment.confirmed,
            status=state["upload"]["status"], launch_id=lid,
            message=assessment.detail, checks=assessment.checks,
            state=state, calls=calls)
