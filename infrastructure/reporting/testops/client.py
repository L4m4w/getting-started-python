"""Bounded allurectl subprocess wrapper.

Secrets travel only through the inherited environment (ALLURE_TOKEN), never
through argv, logs or stored state. The caller decides when subprocesses are
allowed to run; nothing here executes implicitly.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

DEFAULT_TIMEOUT_S = 120
UPLOAD_TIMEOUT_S = 1800


@dataclass
class CommandResult:
    code: int | None
    stdout: str
    stderr: str
    error: str | None = None


def locate(explicit=None):
    """allurectl path: explicit arg/env ALLURECTL, then PATH, then ~/.local."""
    candidates = [explicit, os.environ.get("ALLURECTL"),
                  shutil.which("allurectl"),
                  str(Path.home() / ".local" / "bin" / "allurectl")]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(candidate)
    return None


def run(binary, args, token=None, timeout=DEFAULT_TIMEOUT_S):
    """Run allurectl with bounded time. stdout/stderr captured; never echoed."""
    env = dict(os.environ)
    if token:
        env["ALLURE_TOKEN"] = token
    try:
        result = subprocess.run(
            [binary, *args], capture_output=True, text=True, check=False,
            timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return CommandResult(None, "", "", "timeout")
    except OSError:
        return CommandResult(None, "", "", "launch_error")
    return CommandResult(result.returncode, result.stdout or "",
                         result.stderr or "")


def describe(args):
    """Printable command without environment data."""
    return "allurectl " + shlex.join(args)


def _json_payload(stdout):
    try:
        data = json.loads(stdout)
    except ValueError:
        return None
    if isinstance(data, dict):
        for key in ("content", "items", "data", "results"):
            if isinstance(data.get(key), list):
                return data[key]
        return data
    return data if isinstance(data, list) else None


def parse_cases(stdout):
    """Normalize `test-case list -o json` into [{"id": int, "name": str}]."""
    payload = _json_payload(stdout)
    if not isinstance(payload, list):
        payload = [payload] if isinstance(payload, dict) else []
    cases = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        case_id = item.get("id")
        name = item.get("name")
        try:
            case_id = int(case_id)
        except (TypeError, ValueError):
            continue
        cases.append({"id": case_id, "name": name if isinstance(name, str) else ""})
    return cases


def parse_launch_id(stdout):
    payload = _json_payload(stdout)
    item = payload[0] if isinstance(payload, list) and payload else payload
    if isinstance(item, dict):
        try:
            return int(item.get("id"))
        except (TypeError, ValueError):
            return None
    return None


def case_list_args(endpoint, project_id, aql):
    return ["--endpoint", endpoint, "-o", "json", "test-case", "list",
            "--project-id", str(project_id), "-q", aql]


def launch_create_args(endpoint, project_id, name):
    return ["--endpoint", endpoint, "-o", "json", "launch", "create",
            "--project-id", str(project_id), "--launch-name", name]


def launch_get_args(endpoint, launch_id):
    return ["--endpoint", endpoint, "-o", "json", "launch", "get", str(launch_id)]


def launch_list_args(endpoint, project_id, aql):
    return ["--endpoint", endpoint, "-o", "json", "launch", "list",
            "--project-id", str(project_id), "-q", aql]


def upload_args(endpoint, project_id, launch_id, directory):
    return ["--endpoint", endpoint, "upload", "--project-id", str(project_id),
            "--launch-id", str(launch_id), str(directory)]


_STAT_KEYS = ("passed", "failed", "broken", "skipped")


def _stat_counts(item):
    """Per-status counts if readable; None when the schema is unknown.

    `allurectl launch get --format` documents the statistic vocabulary
    (Passed, Failed, Broken, Skipped). The exact JSON layout was not
    verifiable offline, so both a nested statistic/stats object and flat
    keys are accepted; absent or non-integer values yield None, which the
    caller must treat as inconclusive rather than as zero.
    """
    for source in (item.get("statistic"), item.get("stats"), item):
        if not isinstance(source, dict):
            continue
        found = {key: source[key] for key in _STAT_KEYS if key in source}
        if not found:
            continue
        try:
            return {key: int(value) for key, value in found.items()}
        except (TypeError, ValueError):
            return None
    return None


def parse_launch(stdout):
    """Normalize `launch get/list -o json` into launch descriptors.

    Returns {"id", "name", "project_id", "stats"} per launch: id/name are
    parsed like parse_launch_id; project_id accepts projectId/project_id;
    stats is a {status: count} dict or None when unreadable. Any element
    that cannot yield an integer id is skipped.
    """
    payload = _json_payload(stdout)
    items = payload if isinstance(payload, list) else [payload]
    launches = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            launch_id = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        project_id = item.get("projectId", item.get("project_id"))
        try:
            project_id = int(project_id) if project_id is not None else None
        except (TypeError, ValueError):
            project_id = None
        name = item.get("name")
        launches.append({
            "id": launch_id,
            "name": name if isinstance(name, str) else None,
            "project_id": project_id,
            "stats": _stat_counts(item)})
    return launches


def parse_launch_results(stdout):
    """Normalize a per-launch result listing when a transport provides one.

    No documented allurectl 2.24.0 command lists launch results, so this
    helper exists for transports that expose the documented TestOps read
    API. Entries yield {"name", "status", "test_case_id"}; unreadable
    payloads or unexpected shapes return None (inconclusive), never a
    guessed partial list.
    """
    payload = _json_payload(stdout)
    items = payload if isinstance(payload, list) else None
    if items is None:
        return None
    results = []
    for item in items:
        if not isinstance(item, dict):
            return None
        name = item.get("name")
        status = item.get("status")
        if not isinstance(name, str) or not isinstance(status, str):
            return None
        case_id = item.get("testCaseId", item.get("test_case_id"))
        if case_id is None and isinstance(item.get("testCase"), dict):
            case_id = item["testCase"].get("id")
        try:
            case_id = int(case_id) if case_id is not None else None
        except (TypeError, ValueError):
            return None
        results.append({"name": name, "status": status.lower(),
                        "test_case_id": case_id})
    return results
