"""Scan allure-results, map results to pilot scenarios, build upload packages.

TestOps binds a result to a test case by the ALLURE_ID label or by the
signature derived from `fullName`/`testCaseId`. allure-pytest 2.16 computes
`testCaseId = md5(fullName)` and `fullName` intentionally excludes parameter
values, so six pilot scenarios produced by two parametrized functions carry
only two signatures. Package building therefore rewrites the per-scenario
signature inside a copy of the results; source files are never modified.

Scanning and packaging are strict: corrupt or incomplete result files,
unmapped or duplicated results, digest mismatches against the recorded
plan, and missing or escaping attachments raise ResultsIntegrityError
instead of producing a partial package. Packages are assembled in a
temporary directory and moved into place only after every check passes.
"""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import tempfile

RESULT_SUFFIX = "-result.json"
CONTAINER_SUFFIX = "-container.json"
ALLURE_ID_LABEL = "ALLURE_ID"
LEGACY_ID_LABEL = "as_id"


class ResultsIntegrityError(Exception):
    """Strict allure-results/package validation failed.

    Raised for corrupt or incomplete result files, results that do not map
    one-to-one to the agreed scenarios, assignments that do not cover the
    scanned results exactly, input digests differing from the recorded
    plan, missing or escaping attachments, and source changes detected
    during the build. Messages name offending files and uuids only; no
    result payloads or secrets are included.
    """


def load_results(results_dir):
    """Return [(path, data)] for every *-result.json, sorted by name.

    Strict: an unreadable file, a non-object payload, a missing string
    `uuid` or a duplicated `uuid` raises ResultsIntegrityError rather than
    being silently skipped, so a partial scan can never pass as complete.
    """
    results_dir = Path(results_dir)
    found, problems, seen = [], [], {}
    for path in sorted(results_dir.glob(f"*{RESULT_SUFFIX}")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            problems.append(
                f"{path.name}: unreadable or invalid JSON ({error})")
            continue
        if not isinstance(data, dict):
            problems.append(f"{path.name}: result JSON is not an object")
            continue
        uuid = data.get("uuid")
        if not isinstance(uuid, str) or not uuid:
            problems.append(f"{path.name}: missing string 'uuid'")
            continue
        if uuid in seen:
            problems.append(
                f"{path.name}: duplicate uuid also used by {seen[uuid]}")
            continue
        seen[uuid] = path.name
        found.append((path, data))
    if problems:
        raise ResultsIntegrityError(
            "invalid allure results: " + "; ".join(problems))
    return found


def _parameter_value(data, param_name):
    """Raw python value of one Allure parameter; None when absent/unreadable."""
    for param in data.get("parameters") or []:
        if isinstance(param, dict) and param.get("name") == param_name:
            try:
                return ast.literal_eval(param.get("value") or "None")
            except (ValueError, SyntaxError):
                return param.get("value")
    return None


def _match_scenario(data, index):
    """Scenario ID matching the result signature, or None."""
    for scenario_id, signature in index.items():
        if (data.get("fullName") == signature["full_name"]
                and _parameter_value(data, signature["param"])
                == signature["value"]):
            return scenario_id
    return None


def map_scenarios(results, index):
    """Map loaded results to scenario IDs.

    `index` maps scenario_id -> {"full_name": str, "param": str,
    "value": raw python value}. Returns (mapped, unmapped) where mapped is
    scenario_id -> result dict and unmapped is a list of result uuids.
    Results matching nothing and results duplicating an already mapped
    scenario go to `unmapped`; uuids are guaranteed present because
    load_results enforces them.
    """
    mapped, unmapped = {}, []
    for _path, data in results:
        target = _match_scenario(data, index)
        if target is None or target in mapped:
            unmapped.append(data.get("uuid"))
        else:
            mapped[target] = data
    return mapped, unmapped


def scan_assignments(results_dir, index):
    """Strictly map every result file to exactly one scenario.

    Returns {uuid: scenario_id}. Raises ResultsIntegrityError on scan
    problems, on a result matching no scenario and on a scenario matched
    by more than one result.
    """
    problems, mapping = [], {}
    for path, data in load_results(results_dir):
        uuid = data["uuid"]
        target = _match_scenario(data, index)
        if target is None:
            problems.append(
                f"{path.name} uuid={uuid}: matches no scenario")
        elif target in mapping.values():
            problems.append(
                f"{path.name} uuid={uuid}: scenario {target} already "
                "matched by another result")
        else:
            mapping[uuid] = target
    if problems:
        raise ResultsIntegrityError(
            "results do not map one-to-one to scenarios: "
            + "; ".join(problems))
    return mapping


def results_digest(results_dir):
    """SHA-256 over sorted (name, file hash) pairs; identifies the package."""
    results_dir = Path(results_dir)
    digest = hashlib.sha256()
    for path in sorted(results_dir.iterdir()):
        if not path.is_file():
            continue
        file_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        digest.update(f"{path.name}:{file_hash}\n".encode("utf-8"))
    return digest.hexdigest()


def scenario_full_name(base_full_name, scenario_id):
    return f"{base_full_name}[{scenario_id}]"


def _md5(text):
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def rewrite_result(data, scenario_id, case_id=None):
    """Return a copy of a result with a per-scenario signature.

    `name` gains the scenario prefix so cases stay discoverable by AQL;
    `fullName`, `testCaseId` and `historyId` become scenario-scoped so six
    scenarios cannot collapse into two shared cases. `case_id` adds the
    ALLURE_ID binding label for the documented explicit-link mode.
    """
    rewritten = dict(data)
    base_full_name = data.get("fullName") or ""
    full_name = scenario_full_name(base_full_name, scenario_id)
    params = json.dumps(data.get("parameters") or [], sort_keys=True)
    rewritten["fullName"] = full_name
    rewritten["testCaseId"] = _md5(full_name)
    rewritten["historyId"] = _md5(f"{full_name}:{params}")
    rewritten["name"] = f"{scenario_id}: {data.get('name') or ''}"
    labels = [label for label in data.get("labels") or []
              if not (isinstance(label, dict)
                      and label.get("name") in (ALLURE_ID_LABEL, LEGACY_ID_LABEL))]
    if case_id is not None:
        labels = [*labels, {"name": ALLURE_ID_LABEL, "value": str(case_id)}]
    rewritten["labels"] = labels
    return rewritten


def _load_containers(results_dir):
    """Strictly parsed [(path, data)] for every *-container.json."""
    containers, problems = [], []
    for path in sorted(Path(results_dir).glob(f"*{CONTAINER_SUFFIX}")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            problems.append(
                f"{path.name}: unreadable or invalid JSON ({error})")
            continue
        if not isinstance(data, dict):
            problems.append(f"{path.name}: container JSON is not an object")
            continue
        containers.append((path, data))
    if problems:
        raise ResultsIntegrityError(
            "invalid allure containers: " + "; ".join(problems))
    return containers


def _attachment_entries(node):
    """Yield every attachments[] entry found at any depth of the document."""
    if isinstance(node, dict):
        attachments = node.get("attachments")
        if isinstance(attachments, list):
            yield from attachments
        for value in node.values():
            yield from _attachment_entries(value)
    elif isinstance(node, list):
        for item in node:
            yield from _attachment_entries(item)


def validate_attachments(results_dir, scanned_results):
    """Every referenced attachment must exist inside results_dir.

    Covers top-level and nested step attachments in result files plus
    befores/afters fixture steps in container files. An attachment entry
    without a string source, a source resolving outside the directory or a
    source pointing at a missing file raises ResultsIntegrityError.
    """
    base = Path(results_dir).resolve()
    problems = []
    owners = [(path.name, data) for path, data in scanned_results]
    owners += [(path.name, data)
               for path, data in _load_containers(results_dir)]
    for owner, data in owners:
        for entry in _attachment_entries(data):
            source = entry.get("source") if isinstance(entry, dict) else None
            if not isinstance(source, str) or not source:
                problems.append(
                    f"{owner}: attachment without a source name")
                continue
            resolved = (base / source).resolve()
            if not resolved.is_relative_to(base):
                problems.append(
                    f"{owner}: attachment {source!r} escapes the results "
                    "directory")
            elif not resolved.is_file():
                problems.append(
                    f"{owner}: attachment {source!r} is missing")
    if problems:
        raise ResultsIntegrityError(
            "attachment check failed: " + "; ".join(problems))


def _normalize_assignments(assignments):
    """{uuid: (scenario_id, case_id_or_None)} with a strict shape check."""
    normalized = {}
    for uuid, pair in (assignments or {}).items():
        try:
            scenario_id, case_id = pair
        except (TypeError, ValueError):
            raise ResultsIntegrityError(
                f"assignment for result {uuid} must be a "
                "(scenario_id, testops_id_or_None) pair") from None
        if not isinstance(scenario_id, str) or not scenario_id:
            raise ResultsIntegrityError(
                f"assignment for result {uuid} has no scenario_id")
        normalized[str(uuid)] = (scenario_id, case_id)
    return normalized


def assignments_digest(assignments):
    """Deterministic identity of the uuid -> (scenario, case_id) mapping."""
    normalized = _normalize_assignments(assignments)
    digest = hashlib.sha256()
    for uuid in sorted(normalized):
        scenario_id, case_id = normalized[uuid]
        marker = "" if case_id is None else str(case_id)
        digest.update(f"{uuid}|{scenario_id}|{marker}\n".encode("utf-8"))
    return digest.hexdigest()


def _check_assignments(scanned, normalized, index):
    """Every result must be assigned exactly once to its scenario."""
    problems, uuids, claimed = [], set(), {}
    for path, data in scanned:
        uuid = data["uuid"]
        uuids.add(uuid)
        if uuid not in normalized:
            problems.append(f"{path.name} uuid={uuid}: no assignment")
        if index is None:
            continue
        target = _match_scenario(data, index)
        if target is None:
            problems.append(f"{path.name} uuid={uuid}: matches no scenario")
            continue
        if target in claimed:
            problems.append(
                f"{path.name} uuid={uuid}: scenario {target} already "
                f"matched by uuid {claimed[target]}")
        else:
            claimed[target] = uuid
        if uuid in normalized and normalized[uuid][0] != target:
            problems.append(
                f"{path.name} uuid={uuid}: assigned to "
                f"{normalized[uuid][0]} but maps to {target}")
    for uuid in sorted(set(normalized) - uuids):
        problems.append(f"assignment for unknown result uuid {uuid}")
    if problems:
        raise ResultsIntegrityError(
            "assignments do not match the scanned results: "
            + "; ".join(problems))


def _write_package(results_dir, temp_dir, payloads, normalized):
    files = 0
    for path in sorted(results_dir.iterdir()):
        if not path.is_file():
            continue
        if path.name in payloads:
            data = payloads[path.name]
            scenario_id, case_id = normalized[data["uuid"]]
            rewritten = rewrite_result(data, scenario_id, case_id)
            (temp_dir / path.name).write_text(
                json.dumps(rewritten, ensure_ascii=False), encoding="utf-8")
        else:
            shutil.copy2(path, temp_dir / path.name)
        files += 1
    return files


def _build(results_dir, destination, assignments, *, expected_digest, index):
    results_dir, destination = Path(results_dir), Path(destination)
    if not results_dir.is_dir():
        raise ResultsIntegrityError(
            f"results directory not found: {results_dir}")
    try:
        input_digest = results_digest(results_dir)
    except OSError as error:
        raise ResultsIntegrityError(
            f"cannot hash results directory: {error}") from error
    if expected_digest is not None and input_digest != expected_digest:
        raise ResultsIntegrityError(
            "results changed since the recorded plan "
            f"(expected sha256 {expected_digest}, got {input_digest})")
    normalized = _normalize_assignments(assignments)
    scanned = load_results(results_dir)
    _check_assignments(scanned, normalized, index)
    validate_attachments(results_dir, scanned)
    payloads = {path.name: data for path, data in scanned}
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(
        prefix=f".{destination.name}.tmp-", dir=destination.parent))
    try:
        files = _write_package(results_dir, temp_dir, payloads, normalized)
        if results_digest(results_dir) != input_digest:
            raise ResultsIntegrityError(
                "results changed while the package was being built")
        package_sha256 = results_digest(temp_dir)
        if destination.exists():
            shutil.rmtree(destination)
        temp_dir.rename(destination)
        temp_dir = None
    finally:
        if temp_dir is not None:
            shutil.rmtree(temp_dir, ignore_errors=True)
    return {"files": files, "results": len(normalized),
            "sha256": package_sha256, "input_sha256": input_digest,
            "assignments_sha256": assignments_digest(normalized)}


def build_package(results_dir, destination, assignments):
    """Copy results_dir into destination applying per-scenario rewrites.

    `assignments` maps result uuid -> (scenario_id, testops_id_or_None).
    Strict: fails unless assignments cover every scanned result exactly
    once and all referenced attachments exist inside the source directory.
    Kept for the existing cmd_package call; prefer build_package_verified
    so the build is additionally pinned to the recorded plan digest and
    the scenario index. Returns identity fields for state: files/results/
    sha256 of the package plus input_sha256 and assignments_sha256.
    """
    return _build(results_dir, destination, assignments,
                  expected_digest=None, index=None)


def build_package_verified(results_dir, destination, *, expected_digest,
                           assignments, index=None):
    """Build the upload package only from the exact planned input.

    Raises ResultsIntegrityError when the current input digest differs
    from `expected_digest` recorded by the plan, when `assignments` do not
    cover every scanned result exactly once (and, with `index`, disagree
    with a fresh scenario mapping), when a referenced attachment is
    missing or escapes the source directory, or when the source changes
    while the package is being built. The package is assembled in a
    temporary directory and renamed into place only after all checks
    pass; the previous package is removed only by a successful build, so
    a failed build can never leave a partial or mislabelled package.
    Source files are never modified. Returns {"files", "results",
    "sha256", "input_sha256", "assignments_sha256"} — enough for state to
    record input digest, mapping identity and package digest together.
    """
    return _build(results_dir, destination, assignments,
                  expected_digest=expected_digest, index=index)


def verify_source_digest(results_dir, expected_digest):
    """Raise unless the recorded input is still byte-identical.

    Pre-upload freshness check: compare the package's input_sha256
    against the current results directory before trusting the package.
    """
    if results_digest(results_dir) != expected_digest:
        raise ResultsIntegrityError(
            "results changed since the package was built; rebuild and "
            "review before upload")


def verify_package(package_dir, expected_sha256):
    """Raise unless the built package is still byte-identical."""
    package_dir = Path(package_dir)
    if not package_dir.is_dir():
        raise ResultsIntegrityError(
            f"package directory missing: {package_dir}")
    if results_digest(package_dir) != expected_sha256:
        raise ResultsIntegrityError(
            "package content changed after build; rebuild and review "
            "before upload")
