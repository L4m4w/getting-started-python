"""Per-execution TestOps state: persisted under artifacts/testops/<id>/.

The state file records identity of the result package, scenario bindings,
launch reference and upload outcome. Re-planning never creates external
entities, a confirmed upload of the same package is never re-sent, and an
unknown upload outcome requires verification before any retry.

Schema 2 models the upload lifecycle explicitly: every attempt records the
external phase it reached (`launch_create` or `upload`), proven failures
(`failed`) are separated from indeterminate outcomes (`unknown`), and a
delivered batch waits in `sent` until server-side confirmation promotes it
to `uploaded`. A corrupted or unsupported state file is a hard error, never
a silent fresh state.
"""
from datetime import datetime, timezone
import json
from pathlib import Path

SCHEMA_VERSION = 2
UPLOAD_STATUSES = ("pending", "in_progress", "sent", "uploaded",
                   "failed", "unknown")
ATTEMPT_PHASES = ("launch_create", "upload")
BINDING_STATUSES = ("unresolved", "bound", "ambiguous")
CONFIRMATION_VERDICTS = ("confirmed", "partial", "empty", "contradiction",
                         "inconclusive", "missing", "unreachable")


class StateCorruptError(Exception):
    """The state file exists but cannot be read or parsed."""


class StateSchemaError(StateCorruptError):
    """The state file uses an unsupported schema version or values."""


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _upload_defaults():
    return {"status": "pending", "phase": None, "attempts": 0,
            "started_at": None, "finished_at": None, "exit_code": None,
            "package_sha256": None, "log": None, "detail": None,
            "history": [], "confirmation": None, "abandoned": []}


def new_state(execution_id, endpoint, project_id):
    return {
        "schema_version": SCHEMA_VERSION,
        "execution_id": execution_id,
        "endpoint": endpoint,
        "project_id": project_id,
        "updated_at": _utc_now(),
        "results": None,
        "scenarios": {},
        "unmapped": [],
        "package": None,
        "launch": None,
        "upload": _upload_defaults(),
    }


def state_path(state_dir):
    return Path(state_dir) / "state.json"


def _migrate_v1(data):
    """Upgrade a schema-1 state in memory; never loses launch/attempt data.

    A v1 `failed` upload may have written a launch or a partial batch even
    without a recorded ID, so it migrates to `unknown` (retry blocked). A v1
    `uploaded` is preserved as terminal but flagged as confirmed only by
    the CLI exit code, not by server-side verification.
    """
    migrated = dict(data)
    migrated["schema_version"] = SCHEMA_VERSION
    migrated["migrated_from"] = 1
    migrated["migrated_at"] = _utc_now()
    upload = _upload_defaults()
    upload.update(data.get("upload") or {})
    upload.setdefault("history", [])
    upload.setdefault("abandoned", [])
    upload.setdefault("confirmation", None)
    upload.setdefault("phase", None)
    upload.setdefault("detail", None)
    status = upload.get("status")
    if status not in UPLOAD_STATUSES:
        status = "unknown"
        upload["detail"] = "unrecognized v1 status coerced to unknown"
    if status == "failed":
        upload["status"] = "unknown"
        upload["detail"] = ("v1 failed migrates to unknown: the old implementation "
                            "did not prove absence of external writes")
    else:
        upload["status"] = status
    if status == "uploaded" and upload["confirmation"] is None:
        upload["confirmation"] = {
            "verdict": "confirmed", "method": "migrated",
            "detail": "v1 uploaded was confirmed only by the allurectl exit "
                      "code; no server-side result-set check was recorded",
            "checked_at": migrated["migrated_at"]}
    migrated["upload"] = upload
    return migrated


def migrate_state(data):
    """Return a schema-2 state or raise StateSchemaError."""
    version = data.get("schema_version")
    if version == 1:
        data = _migrate_v1(data)
    elif version != SCHEMA_VERSION:
        raise StateSchemaError(
            f"unsupported state schema_version: {version!r}")
    upload = data.get("upload")
    if not isinstance(upload, dict):
        raise StateSchemaError("state has no 'upload' object")
    if upload.get("status") not in UPLOAD_STATUSES:
        raise StateSchemaError(
            f"unsupported upload status: {upload.get('status')!r}")
    return data


def load_state(state_dir):
    """Load and migrate state; None only when the file does not exist.

    Raises StateCorruptError on unreadable/invalid JSON and
    StateSchemaError on an unsupported schema — callers must surface the
    block instead of silently starting a fresh state.
    """
    path = state_path(state_dir)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise StateCorruptError(f"state file unreadable: {path}: {error}")
    try:
        data = json.loads(text)
    except ValueError as error:
        raise StateCorruptError(f"state file is not valid JSON: {path}") \
            from error
    if not isinstance(data, dict):
        raise StateCorruptError(f"state file is not a JSON object: {path}")
    return migrate_state(data)


def load_state_or_error(state_dir):
    """(state, error): tolerant variant for callers that print diagnostics."""
    try:
        return load_state(state_dir), None
    except StateCorruptError as error:
        return None, error


def save_state(state_dir, state):
    state_dir = Path(state_dir)
    state_dir.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _utc_now()
    path = state_path(state_dir)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    temporary.replace(path)
    return path


def record_results(state, results_dir, digest, files, mapped, unmapped):
    """Refresh plan data while preserving bindings and upload progress."""
    previous = state.get("scenarios") or {}
    state["results"] = {"path": str(results_dir), "sha256": digest,
                        "files": files, "results": len(mapped)}
    scenarios = {}
    for scenario_id, result in sorted(mapped.items()):
        prior = previous.get(scenario_id) or {}
        scenarios[scenario_id] = {
            "uuid": result.get("uuid"),
            "status": result.get("status"),
            "testops_id": prior.get("testops_id"),
            "binding": prior.get("binding") or "unresolved",
            "binding_source": prior.get("binding_source"),
        }
    state["scenarios"] = scenarios
    state["unmapped"] = [uuid for uuid in unmapped if uuid]
    return state


def set_binding(state, scenario_id, testops_id, source):
    """Assign a TestOps ID; raises ValueError on conflicts."""
    entry = (state.get("scenarios") or {}).get(scenario_id)
    if entry is None:
        raise ValueError(f"unknown scenario: {scenario_id}")
    current = entry.get("testops_id")
    if current is not None and current != testops_id:
        raise ValueError(
            f"{scenario_id} already bound to {current}; re-plan or reassign")
    if any(other.get("testops_id") == testops_id
           for key, other in state["scenarios"].items() if key != scenario_id):
        raise ValueError(f"TestOps ID {testops_id} already bound elsewhere")
    entry["testops_id"] = testops_id
    entry["binding"] = "bound"
    entry["binding_source"] = source
    return state


def mark_ambiguous(state, scenario_id):
    if scenario_id in state.get("scenarios", {}):
        state["scenarios"][scenario_id]["binding"] = "ambiguous"
    return state


def unresolved_ids(state):
    return [key for key, entry in (state.get("scenarios") or {}).items()
            if entry.get("binding") != "bound" or entry.get("testops_id") is None]


def record_package(state, package_dir, info, mode):
    state["package"] = {"dir": str(package_dir), "sha256": info["sha256"],
                        "files": info["files"], "results": info["results"],
                        "mode": mode, "built_at": _utc_now(),
                        "input_sha256": info.get("input_sha256"),
                        "assignments_sha256": info.get("assignments_sha256")}
    return state


def can_upload(state):
    """(allowed, reason). Confirmed or unresolved uploads are never repeated."""
    upload = state.get("upload") or {}
    status = upload.get("status")
    if status == "uploaded":
        return False, "upload already confirmed for this execution"
    if status == "sent":
        return False, ("batch already delivered to the recorded launch; "
                       "run verify before any re-send")
    if status == "unknown":
        return False, ("previous upload outcome unknown; run verify before "
                       "any retry to avoid duplicating the launch")
    if status == "in_progress":
        return False, "upload is marked in_progress; inspect and resolve first"
    if status == "failed" and upload.get("attempts"):
        return "retry", "previous upload failed; retry requires --retry"
    if state.get("package") is None:
        return False, "no upload package built yet"
    if status == "failed":
        return False, "upload is marked failed without attempts; resolve first"
    return True, None


def expected_scenarios(state):
    """scenario_id -> {"status", "testops_id"} expected on the server."""
    expected = {}
    for scenario_id, entry in (state.get("scenarios") or {}).items():
        expected[scenario_id] = {"status": entry.get("status"),
                                 "testops_id": entry.get("testops_id")}
    return expected


def expected_stats(state):
    """Expected per-status result counts derived from mapped scenarios."""
    counts = {}
    for entry in expected_scenarios(state).values():
        status = entry.get("status")
        if status:
            counts[status] = counts.get(status, 0) + 1
    return counts


def begin_upload_attempt(state, package_sha256):
    """Mark an attempt as started; persist before any external call."""
    upload = state["upload"]
    upload["status"] = "in_progress"
    upload["phase"] = None
    upload["attempts"] = (upload.get("attempts") or 0) + 1
    upload["started_at"] = _utc_now()
    upload["finished_at"] = None
    upload["exit_code"] = None
    upload["detail"] = None
    upload["package_sha256"] = package_sha256
    return state


def mark_upload_started(state, package_sha256):
    """Compatibility wrapper for begin_upload_attempt."""
    return begin_upload_attempt(state, package_sha256)


def set_attempt_phase(state, phase):
    """Record which external operation is in flight for this attempt."""
    if phase not in ATTEMPT_PHASES:
        raise ValueError(f"unknown attempt phase: {phase!r}")
    if state["upload"].get("status") != "in_progress":
        raise ValueError("attempt phase requires an in_progress upload")
    state["upload"]["phase"] = phase
    return state


def complete_attempt(state, status, exit_code=None, log=None, detail=None):
    """Finish the current attempt and append it to upload history."""
    if status not in UPLOAD_STATUSES:
        raise ValueError(f"unknown upload status: {status!r}")
    if status in ("pending", "in_progress"):
        raise ValueError("an attempt can only finish as sent/uploaded/"
                         "failed/unknown")
    upload = state["upload"]
    upload["status"] = status
    upload["finished_at"] = _utc_now()
    upload["exit_code"] = exit_code
    if log is not None:
        upload["log"] = str(log)
    if detail is not None:
        upload["detail"] = detail
    history = upload.setdefault("history", [])
    history.append({
        "attempt": upload.get("attempts"),
        "phase": upload.get("phase"),
        "status": status,
        "exit_code": exit_code,
        "started_at": upload.get("started_at"),
        "finished_at": upload["finished_at"],
        "package_sha256": upload.get("package_sha256"),
        "detail": detail,
    })
    return state


def mark_upload_finished(state, status, exit_code, log=None):
    """Compatibility wrapper for complete_attempt."""
    return complete_attempt(state, status, exit_code, log)


def record_launch(state, launch_id, name, url, source=None):
    """Record the server-side launch; retrying never replaces this ID.

    The create path keeps the exact schema-1 shape; a non-None `source`
    (e.g. "adopted") is added only for operator-recorded launches.
    """
    launch = {"id": launch_id, "name": name, "url": url,
              "created_at": _utc_now()}
    if source is not None:
        launch["source"] = source
    state["launch"] = launch
    return state


def adopt_launch(state, launch_id, name=None, url=None):
    """Record a launch found manually (e.g. after an unreadable create)."""
    try:
        launch_id = int(launch_id)
    except (TypeError, ValueError):
        raise ValueError(f"launch ID must be numeric: {launch_id!r}")
    existing = state.get("launch") or {}
    if existing.get("id") is not None and existing.get("id") != launch_id:
        raise ValueError(
            f"launch {existing['id']} already recorded; abandon it first")
    return record_launch(state, launch_id, name or existing.get("name"),
                         url or existing.get("url"), source="adopted")


def abandon_launch(state, reason):
    """Move the recorded launch to the audit list and allow a fresh retry.

    Use only after the operator has disposed of the server-side launch
    (deleted it or accepted it as an orphan): the ID is never lost, it is
    preserved under upload.abandoned with the recorded reason.
    """
    launch = state.get("launch")
    if not launch:
        raise ValueError("no recorded launch to abandon")
    upload = state["upload"]
    upload.setdefault("abandoned", []).append(
        {**launch, "abandoned_at": _utc_now(), "reason": str(reason)})
    state["launch"] = None
    upload["status"] = "failed"
    upload["detail"] = f"launch {launch.get('id')} abandoned: {reason}"
    return state


def resolve_in_progress(state, note):
    """Explicit operator transition: a stale in_progress becomes unknown.

    Never called implicitly: a recorded in_progress means an attempt may
    still be running or may have died after an external write, so the
    honest post-crash status is unknown, requiring verification.
    """
    upload = state["upload"]
    if upload.get("status") != "in_progress":
        raise ValueError("resolve_in_progress requires status in_progress")
    return complete_attempt(
        state, "unknown", upload.get("exit_code"),
        detail=f"in_progress resolved manually: {note}")


def record_confirmation(state, verdict, method, detail=None, checks=None):
    """Store verification evidence without changing the upload status."""
    if verdict not in CONFIRMATION_VERDICTS:
        raise ValueError(f"unknown confirmation verdict: {verdict!r}")
    state["upload"]["confirmation"] = {
        "verdict": verdict, "method": method, "detail": detail,
        "checks": dict(checks or {}), "checked_at": _utc_now()}
    return state


def mark_upload_confirmed(state, method, detail=None, checks=None):
    """Promote a delivered batch to uploaded with recorded evidence."""
    record_confirmation(state, "confirmed", method, detail, checks)
    state["upload"]["status"] = "uploaded"
    state["upload"]["finished_at"] = _utc_now()
    return state
