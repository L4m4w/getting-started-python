"""Workflow state: versioned schema, canonical digests and atomic IO.

One ``state.json`` per workflow directory is the only versioned record of
identity, accepted artifacts, executions, publications, intents and the
audit journal. Loading never repairs silently: corrupt JSON, an unknown
schema version or an inconsistent phase is a hard error and the file is
left untouched. Saving validates first, then writes ``.tmp`` +
``fsync`` + ``os.replace`` and syncs the directory.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

WORKFLOW_SCHEMA_VERSION = 1
PHASES = ("initialized", "context_ready", "scenarios_ready",
          "awaiting_review", "approved", "implementation_ready",
          "executed", "published")
PHASE_STATUSES = ("active", "blocked", "failed")
ARTIFACT_KINDS = ("context", "scenarios", "review", "implementation",
                  "bindings")
ARTIFACT_STATUSES = ("pending", "accepted", "stale")
ACTORS = ("human", "llm", "orchestrator", "imported")
INTENT_OPERATIONS = ("run.execution", "testops.upload", "testops.verify",
                     "pr.create", "pr.search")
INTENT_STATUSES = ("declared", "dispatched", "completed", "failed",
                   "unknown")
EXECUTION_STATUSES = ("completed", "failed", "unknown")
EXECUTION_SOURCES = ("orchestrated", "imported")
EXECUTION_VARIANTS = ("base", "head")
HEAD_KINDS = ("commit", "patch", "none")
PR_STATUSES = ("pending", "intent", "created", "verified", "unknown",
               "blocked")
REVIEW_DECISIONS = ("approved", "needs_decision", "rejected")
BINDING_SOURCES = ("assign", "resolve", "imported")

# Fixed-MVP domains used by the run and publication gates: the only
# selection scope the gates enforce, the junit summary counters every
# recorded execution carries and the PR roles that must all be required.
REQUIRED_EXECUTION_SCOPE = "api"
JUNIT_SUMMARY_KEYS = ("total", "passed", "failed", "errors", "skipped")
PR_ROLES = ("app", "tests")

HEX40_64 = re.compile(r"[0-9a-f]{40,64}")
HEX64 = re.compile(r"[0-9a-f]{64}")
WORKFLOW_ID_RE = re.compile(r"wf-[0-9a-f]{16}")
PILOT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
EXECUTION_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")

# Dependency contract for the stale cascade. ``inputs`` are keys of the
# input digest map (``identity`` plus every revision_data key);
# ``artifacts`` are other artifact kinds. Freshness is recomputed from
# bound digests, never trusted from ``bound_revision`` alone.
ARTIFACT_DEPENDENCIES = {
    "context": {"inputs": ["identity", "app_head"], "artifacts": []},
    "scenarios": {"inputs": ["requirements"], "artifacts": ["context"]},
    "review": {"inputs": [], "artifacts": ["scenarios"]},
    "implementation": {"inputs": ["tests_repo"],
                       "artifacts": ["review", "scenarios"]},
    "bindings": {"inputs": [], "artifacts": ["scenarios"]},
}
UNFINISHED_INTENT_STATUSES = ("declared", "dispatched", "unknown")


class WorkflowError(Exception):
    """Blocked condition; the CLI surfaces it as exit 69."""


class WorkflowStateCorruptError(WorkflowError):
    """The state or index file exists but cannot be read or parsed."""


class WorkflowSchemaError(WorkflowStateCorruptError):
    """Unsupported schema version, value domain or phase consistency."""


class WorkflowValidationError(WorkflowError):
    """An accepted input (envelope, CLI value, state mutation) is invalid."""


class WorkflowBlockedError(WorkflowError):
    """A guard, gate or lock refused the operation."""


class WorkflowLaunchError(WorkflowError):
    """The delegated process could not start; exit 127 at the CLI."""


class WorkflowPermissionError(WorkflowError):
    """A required explicit permission flag is missing; exit 77."""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)


def canonical_digest(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _is_hex(value, pattern):
    return isinstance(value, str) and bool(pattern.fullmatch(value))


def require_hex64(value, field):
    if not _is_hex(value, HEX64):
        raise WorkflowValidationError(f"{field}: expected 64-hex sha256")
    return value.lower()


def require_git_sha(value, field):
    if not _is_hex(value, HEX40_64):
        raise WorkflowValidationError(f"{field}: expected 40-64 hex SHA")
    return value.lower()


def normalize_repo_key(repo):
    """Canonical repo key: normalized transport/host forms, path case kept.

    ``https://``, ``http://``, ``ssh://`` and ``git@host:path`` spellings of
    the same remote collapse to ``host/path`` with the host lowercased and a
    trailing ``.git``/``/`` removed. Local paths are normalized with
    ``os.path.normpath`` only — meaningful path components keep their case.
    """
    if not isinstance(repo, str) or not repo.strip():
        raise WorkflowValidationError("app_repo must be a non-empty string")
    repo = repo.strip()
    if repo.startswith("git@") and ":" in repo[4:]:
        host, _, path = repo[4:].partition(":")
        key = host.lower() + "/" + path
    elif "://" in repo:
        parts = urlsplit(repo)
        key = (parts.hostname or "").lower() + (parts.path or "")
    else:
        key = os.path.normpath(repo)
    key = key.rstrip("/")
    if key.endswith(".git"):
        key = key[:-4]
    return key or repo


def workflow_id_for(pilot_id, repo_key, base_sha):
    material = ("wf-v1\x00" + pilot_id + "\x00" + repo_key + "\x00"
                + base_sha.lower())
    return "wf-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def input_digest_map(identity, revision_data):
    """Per-input digests used by artifact bindings and the T8 cascade."""
    digests = {"identity": canonical_digest(identity)}
    for key, value in sorted((revision_data or {}).items()):
        digests[key] = canonical_digest(value)
    return digests


def revision_data_digest(revision_data):
    return canonical_digest(revision_data)


def new_state(pilot_id, app_repo, app_base_sha, revision_data, *,
              app_repo_path=None, supersedes=None, inherited_intents=None,
              tests_repo_path=None):
    repo_key = normalize_repo_key(app_repo)
    identity = {"pilot_id": pilot_id, "app_repo": repo_key,
                "app_base_sha": app_base_sha.lower()}
    workflow_id = workflow_id_for(pilot_id, repo_key, app_base_sha)
    now = utc_now()
    state = {
        "workflow_schema_version": WORKFLOW_SCHEMA_VERSION,
        "workflow_id": workflow_id,
        "supersedes": supersedes,
        "inherited_intents": list(inherited_intents or []),
        "created_at": now,
        "updated_at": now,
        "phase": "initialized",
        "phase_status": "active",
        "blocked_reason": None,
        "input": {
            "revision": 1,
            "identity": identity,
            "locals": {"app_repo_path": app_repo_path,
                       "tests_repo_path": tests_repo_path},
            "revision_data": revision_data,
            "history": [{"revision": 1, "recorded_at": now,
                         "revision_data_sha256":
                             revision_data_digest(revision_data)}],
        },
        "artifacts": {kind: {"status": "pending"} for kind in ARTIFACT_KINDS},
        "executions": [],
        "publications": {
            "testops": {"required": True, "execution_id": None,
                        "last_observation": None},
            "pr": {role: {"required": True, "status": "pending",
                          "spec_sha256": None, "spec": None,
                          "intent_id": None, "number": None, "url": None}
                   for role in ("app", "tests")},
        },
        "intents": [],
        "errors": [],
        "journal": [],
        "metrics": {"llm_cost": None},
    }
    add_journal(state, "orchestrator", "init",
                f"workflow {workflow_id} revision 1"
                + (f"; supersedes {supersedes}" if supersedes else ""))
    return state


def state_path(workflow_dir):
    return Path(workflow_dir) / "state.json"


def _require(condition, message):
    if not condition:
        raise WorkflowSchemaError(message)


def _require_type(value, kind, message):
    if not isinstance(value, kind):
        raise WorkflowSchemaError(message)
    return value


def _validate_head(head):
    head = _require_type(head, dict, "revision_data.app_head must be an object")
    kind = head.get("kind")
    _require(kind in HEAD_KINDS, f"app_head.kind unsupported: {kind!r}")
    git_sha, sha256 = head.get("git_sha"), head.get("sha256")
    if kind == "commit":
        _require(_is_hex(git_sha, HEX40_64),
                 "app_head kind=commit requires a 40-64 hex git_sha")
    if kind == "patch":
        _require(git_sha is None,
                 "app_head kind=patch forbids git_sha: a dirty snapshot is "
                 "not an immutable head")
        _require(_is_hex(sha256, HEX64),
                 "app_head kind=patch requires a 64-hex sha256")
    if kind == "none":
        _require(git_sha is None and sha256 is None,
                 "app_head kind=none forbids git_sha/sha256")
    if sha256 is not None:
        _require(_is_hex(sha256, HEX64),
                 "app_head.sha256 must be 64-hex")


def _validate_artifact(kind, entry):
    _require_type(entry, dict, f"artifacts.{kind} must be an object")
    status = entry.get("status")
    _require(status in ARTIFACT_STATUSES,
             f"artifacts.{kind}.status unsupported: {status!r}")
    if status == "pending":
        return
    _require(_is_hex(entry.get("artifact_digest"), HEX64),
             f"artifacts.{kind}.artifact_digest must be 64-hex")
    _require_type(entry.get("bound_input_digests"), dict,
                  f"artifacts.{kind}.bound_input_digests must be an object")
    _require_type(entry.get("bound_artifact_digests"), dict,
                  f"artifacts.{kind}.bound_artifact_digests must be an object")
    _require(isinstance(entry.get("accepted_at"), str),
             f"artifacts.{kind}.accepted_at missing")


def _validate_intent(entry):
    _require_type(entry, dict, "intents[] entries must be objects")
    _require(isinstance(entry.get("intent_id"), str) and entry["intent_id"],
             "intent_id missing")
    _require(entry.get("operation") in INTENT_OPERATIONS,
             f"intent operation unsupported: {entry.get('operation')!r}")
    _require(entry.get("status") in INTENT_STATUSES,
             f"intent status unsupported: {entry.get('status')!r}")
    if entry.get("argv_digest") is not None:
        _require(_is_hex(entry["argv_digest"], HEX64),
                 "intent argv_digest must be 64-hex")


def _validate_execution(entry):
    _require_type(entry, dict, "executions[] entries must be objects")
    _require(isinstance(entry.get("execution_id"), str)
             and EXECUTION_ID_RE.fullmatch(entry["execution_id"]),
             f"execution_id invalid: {entry.get('execution_id')!r}")
    _require(entry.get("variant") in EXECUTION_VARIANTS,
             f"execution variant unsupported: {entry.get('variant')!r}")
    _require(entry.get("status") in EXECUTION_STATUSES,
             f"execution status unsupported: {entry.get('status')!r}")
    _require(entry.get("source") in EXECUTION_SOURCES,
             f"execution source unsupported: {entry.get('source')!r}")
    _require(isinstance(entry.get("bound_revision"), int)
             and not isinstance(entry.get("bound_revision"), bool)
             and entry["bound_revision"] >= 0,
             "execution bound_revision must be a non-negative int")
    summary = entry.get("junit_summary")
    if summary is not None:
        _require_type(summary, dict,
                      "executions[].junit_summary must be an object or null")
        missing = [key for key in JUNIT_SUMMARY_KEYS if key not in summary]
        _require(not missing,
                 f"executions[].junit_summary missing keys: {missing}")
        for key, value in summary.items():
            _require(isinstance(key, str) and key,
                     "executions[].junit_summary keys must be strings")
            _require(isinstance(value, int)
                     and not isinstance(value, bool) and value >= 0,
                     f"executions[].junit_summary.{key} must be a "
                     "non-negative int")
    selection = entry.get("selection")
    if selection is not None:
        _require_type(selection, dict,
                      "executions[].selection must be an object or null")
        targets = selection.get("targets")
        if targets is not None:
            _require(isinstance(targets, list)
                     and all(isinstance(t, str) and t for t in targets),
                     "executions[].selection.targets must be a list of "
                     "non-empty strings")
        if selection.get("scope") is not None:
            _require(isinstance(selection["scope"], str),
                     "executions[].selection.scope must be a string")


def _validate_execution_requirement(entry, where):
    """One expected/strength requirement element used by the run gate."""
    _require_type(entry, dict, f"{where} must be an object")
    _require(entry.get("variant") in EXECUTION_VARIANTS,
             f"{where}.variant unsupported: {entry.get('variant')!r}")
    _require(isinstance(entry.get("required"), bool),
             f"{where}.required must be a bool")
    _require(entry.get("scope") == REQUIRED_EXECUTION_SCOPE,
             f"{where}.scope must be {REQUIRED_EXECUTION_SCOPE!r}: it is "
             "the only selection scope the run gate enforces")
    expect = entry.get("expect")
    if expect is not None:
        _require_type(expect, dict, f"{where}.expect must be an object")
        for key, value in expect.items():
            _require(key in JUNIT_SUMMARY_KEYS,
                     f"{where}.expect key unsupported: {key!r}")
            _require(isinstance(value, int)
                     and not isinstance(value, bool) and value >= 0,
                     f"{where}.expect.{key} must be a non-negative int")


def _validate_publications(pubs):
    pubs = _require_type(pubs, dict, "publications must be an object")
    testops = _require_type(pubs.get("testops"), dict,
                            "publications.testops must be an object")
    _require(testops.get("required") is True,
             "publications.testops.required must be true: the fixed MVP "
             "always requires the TestOps publication")
    execution_id = testops.get("execution_id")
    if execution_id is not None:
        _require(isinstance(execution_id, str),
                 "publications.testops.execution_id must be a string")
    obs = testops.get("last_observation")
    if obs is not None:
        _require_type(obs, dict, "last_observation must be an object")
    prs = _require_type(pubs.get("pr"), dict,
                        "publications.pr must be an object")
    _require(set(prs) == set(PR_ROLES),
             f"publications.pr must contain exactly the roles {PR_ROLES}")
    for role in PR_ROLES:
        entry = prs[role]
        _require_type(entry, dict, f"publications.pr.{role} must be an object")
        _require(entry.get("required") is True,
                 f"publications.pr.{role}.required must be true: the fixed "
                 "MVP requires both PR publications")
        _require(entry.get("status") in PR_STATUSES,
                 f"publications.pr.{role}.status unsupported: "
                 f"{entry.get('status')!r}")
        spec = entry.get("spec")
        if spec is not None:
            _require_type(spec, dict,
                          f"publications.pr.{role}.spec must be an object")
        spec_sha256 = entry.get("spec_sha256")
        if spec_sha256 is not None:
            _require(_is_hex(spec_sha256, HEX64),
                     f"publications.pr.{role}.spec_sha256 must be 64-hex")


def artifact_fresh(state, kind, _chain=()):
    """Recomputed freshness: accepted + every bound digest still matching."""
    entry = (state.get("artifacts") or {}).get(kind) or {}
    if entry.get("status") != "accepted":
        return False
    inputs = input_digest_map(state["input"]["identity"],
                              state["input"]["revision_data"])
    for key, digest in (entry.get("bound_input_digests") or {}).items():
        if inputs.get(key) != digest:
            return False
    for dep, digest in (entry.get("bound_artifact_digests") or {}).items():
        dep_entry = (state.get("artifacts") or {}).get(dep) or {}
        if dep_entry.get("artifact_digest") != digest:
            return False
        if dep in _chain or not artifact_fresh(state, dep, _chain + (kind,)):
            return False
    return True


def execution_matches(entry, requirement, revision):
    if (not isinstance(entry, dict) or not isinstance(requirement, dict)
            or entry.get("status") != "completed"
            or not isinstance(entry.get("bound_revision"), int)
            or isinstance(entry.get("bound_revision"), bool)
            or entry["bound_revision"] != revision
            or entry.get("variant") != requirement.get("variant")):
        return False
    summary = entry.get("junit_summary")
    if not isinstance(summary, dict):
        return False
    expect = requirement.get("expect")
    if expect is not None and not isinstance(expect, dict):
        return False
    for key, expected in (expect or {}).items():
        if summary.get(key) != expected:
            return False
    if requirement.get("scope") == REQUIRED_EXECUTION_SCOPE:
        selection = entry.get("selection")
        if not isinstance(selection, dict):
            return False
        targets = selection.get("targets")
        if not isinstance(targets, list):
            return False
        if not any(isinstance(t, str)
                   and (t == "tests/api" or t.startswith("tests/api/"))
                   for t in targets):
            return False
    return True


def executions_satisfy(state):
    """Required run gates: expected executions plus strength evidence."""
    input_ = state.get("input")
    if not isinstance(input_, dict):
        return False
    revision = input_.get("revision")
    revision_data = input_.get("revision_data")
    if not isinstance(revision_data, dict):
        return False
    expected = revision_data.get("expected_executions") or []
    if not isinstance(expected, list):
        return False
    requirements = [item for item in expected
                    if isinstance(item, dict) and item.get("required")]
    strength = revision_data.get("strength_evidence")
    if isinstance(strength, dict) and strength.get("required"):
        requirements.append({"variant": strength.get("variant"),
                             "required": True,
                             "expect": strength.get("expect"),
                             "scope": strength.get("scope")})
    if not requirements:
        return False
    executions = state.get("executions")
    if not isinstance(executions, list):
        return False
    return all(
        any(execution_matches(entry, req, revision) for entry in executions)
        for req in requirements)


def publications_confirmed(state):
    input_ = state.get("input")
    if not isinstance(input_, dict):
        return False
    revision = input_.get("revision")
    revision_data = input_.get("revision_data")
    if not isinstance(revision_data, dict):
        return False
    pubs = state.get("publications")
    if not isinstance(pubs, dict):
        return False
    # The fixed MVP composition is enforced at the gate too, not only in
    # the schema: a state dict that bypasses load_state still cannot claim
    # confirmation from a weakened publication set.
    testops = pubs.get("testops")
    if not isinstance(testops, dict) or testops.get("required") is not True:
        return False
    obs = testops.get("last_observation")
    if not isinstance(obs, dict) or obs.get("upload_status") != "uploaded":
        return False
    # The confirming observation must concern a head execution bound to the
    # current revision — an uploaded run of an older head or a baseline
    # run never confirms head publication.
    execution_id = testops.get("execution_id")
    executions = state.get("executions")
    if not isinstance(executions, list):
        return False
    bound = [entry for entry in executions
             if isinstance(entry, dict)
             and entry.get("execution_id") == execution_id
             and entry.get("bound_revision") == revision
             and entry.get("variant") == "head"]
    if not bound:
        return False
    app_head = revision_data.get("app_head")
    tests_repo = revision_data.get("tests_repo")
    if not isinstance(app_head, dict) or not isinstance(tests_repo, dict):
        return False
    prs = pubs.get("pr")
    if not isinstance(prs, dict) or set(prs) != set(PR_ROLES):
        return False
    for role in PR_ROLES:
        entry = prs[role]
        if (not isinstance(entry, dict)
                or entry.get("required") is not True
                or entry.get("status") != "verified"):
            return False
        spec = entry.get("spec")
        if not isinstance(spec, dict):
            return False
        head_sha = spec.get("head_sha")
        if not _is_hex(head_sha, HEX40_64):
            return False
        if role == "app":
            if app_head.get("kind") != "commit":
                return False
            if head_sha.lower() != (app_head.get("git_sha") or "").lower():
                return False
        else:
            if tests_repo.get("dirty"):
                return False
            if head_sha.lower() != (tests_repo.get("commit") or "").lower():
                return False
    return True


def implied_phase(state):
    """Highest gate provably satisfied by the recorded data."""
    if not artifact_fresh(state, "context"):
        return "initialized"
    if not artifact_fresh(state, "scenarios"):
        return "context_ready"
    review = (state.get("artifacts") or {}).get("review") or {}
    if (not artifact_fresh(state, "review")
            or review.get("decision") != "approved"):
        return "awaiting_review"
    if not artifact_fresh(state, "implementation"):
        return "approved"
    if not executions_satisfy(state):
        return "implementation_ready"
    if not publications_confirmed(state):
        return "executed"
    return "published"


def validate_state(data):
    """Structural, domain and phase-consistency validation."""
    _require_type(data, dict, "state must be a JSON object")
    version = data.get("workflow_schema_version")
    _require(version == WORKFLOW_SCHEMA_VERSION,
             f"unsupported workflow_schema_version: {version!r}")
    identity = _require_type(
        _require_type(data.get("input"), dict, "input must be an object")
        .get("identity"), dict, "input.identity must be an object")
    pilot_id = identity.get("pilot_id")
    _require(isinstance(pilot_id, str)
             and PILOT_ID_RE.fullmatch(pilot_id),
             f"pilot_id invalid: {pilot_id!r}")
    repo_key = identity.get("app_repo")
    _require(isinstance(repo_key, str) and repo_key,
             "identity.app_repo missing")
    base_sha = identity.get("app_base_sha")
    _require(_is_hex(base_sha, HEX40_64),
             "identity.app_base_sha must be 40-64 hex")
    _require(WORKFLOW_ID_RE.fullmatch(data.get("workflow_id") or "")
             and data["workflow_id"]
             == workflow_id_for(pilot_id, repo_key, base_sha),
             "workflow_id does not match the recorded identity")
    _require(data.get("phase") in PHASES,
             f"phase unsupported: {data.get('phase')!r}")
    _require(data.get("phase_status") in PHASE_STATUSES,
             f"phase_status unsupported: {data.get('phase_status')!r}")
    if data.get("phase_status") == "blocked":
        _require(isinstance(data.get("blocked_reason"), str)
                 and data["blocked_reason"],
                 "blocked phase_status requires blocked_reason")
    revision = data["input"].get("revision")
    _require(isinstance(revision, int) and revision >= 1,
             "input.revision must be a positive int")
    revision_data = _require_type(data["input"].get("revision_data"), dict,
                                  "input.revision_data must be an object")
    _validate_head(revision_data.get("app_head"))
    tests_repo = _require_type(revision_data.get("tests_repo"), dict,
                               "revision_data.tests_repo must be an object")
    _require(_is_hex(tests_repo.get("commit"), HEX40_64),
             "tests_repo.commit must be 40-64 hex")
    _require(isinstance(tests_repo.get("dirty"), bool),
             "tests_repo.dirty must be a bool")
    if tests_repo.get("snapshot_sha256") is not None:
        _require(_is_hex(tests_repo["snapshot_sha256"], HEX64),
                 "tests_repo.snapshot_sha256 must be 64-hex")
    requirements = _require_type(revision_data.get("requirements"), dict,
                                 "revision_data.requirements must be an object")
    _require(_is_hex(requirements.get("sha256"), HEX64),
             "requirements.sha256 must be 64-hex")
    ids = requirements.get("ids")
    _require(isinstance(ids, list) and ids
             and all(isinstance(item, str) and item for item in ids),
             "requirements.ids must be a non-empty list of strings")
    expected = revision_data.get("expected_executions")
    if expected is not None:
        _require_type(expected, list,
                      "revision_data.expected_executions must be a list")
        for index, item in enumerate(expected):
            _validate_execution_requirement(
                item, f"revision_data.expected_executions[{index}]")
    strength = revision_data.get("strength_evidence")
    if strength is not None:
        _require_type(strength, dict,
                      "revision_data.strength_evidence must be an object")
        if strength:
            _validate_execution_requirement(
                strength, "revision_data.strength_evidence")
    history = _require_type(data["input"].get("history"), list,
                            "input.history must be a list")
    _require(len(history) >= 1, "input.history must not be empty")
    artifacts = _require_type(data.get("artifacts"), dict,
                              "artifacts must be an object")
    for kind in ARTIFACT_KINDS:
        _validate_artifact(kind, artifacts.get(kind))
    executions = _require_type(data.get("executions"), list,
                               "executions must be a list")
    for entry in executions:
        _validate_execution(entry)
    _validate_publications(data.get("publications"))
    intents = _require_type(data.get("intents"), list,
                            "intents must be a list")
    for entry in intents:
        _validate_intent(entry)
    journal = _require_type(data.get("journal"), list,
                            "journal must be a list")
    seq = 0
    for entry in journal:
        _require_type(entry, dict, "journal entries must be objects")
        _require(isinstance(entry.get("seq"), int)
                 and entry["seq"] == seq + 1,
                 "journal seq must be a gapless sequence from 1")
        seq = entry["seq"]
    _require(data.get("phase") == implied_phase(data),
             f"phase {data.get('phase')!r} is inconsistent with the "
             f"recorded artifacts/executions/publications "
             f"(implied: {implied_phase(data)!r})")
    return data


def load_state(workflow_dir):
    """Validated state or None when absent; corrupt files are hard errors."""
    path = state_path(workflow_dir)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise WorkflowStateCorruptError(
            f"state file unreadable: {path}: {error}") from error
    try:
        data = json.loads(text)
    except ValueError as error:
        raise WorkflowStateCorruptError(
            f"state file is not valid JSON: {path}") from error
    if not isinstance(data, dict):
        raise WorkflowStateCorruptError(
            f"state file is not a JSON object: {path}")
    try:
        return validate_state(data)
    except WorkflowValidationError as error:
        raise WorkflowSchemaError(str(error)) from error


def save_state(workflow_dir, state):
    """Validate, then write tmp + fsync + replace + directory sync."""
    validate_state(state)
    workflow_dir = Path(workflow_dir)
    workflow_dir.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utc_now()
    path = state_path(workflow_dir)
    temporary = path.with_suffix(".tmp")
    payload = (json.dumps(state, indent=2, ensure_ascii=False) + "\n") \
        .encode("utf-8")
    with open(temporary, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    try:
        dir_fd = os.open(workflow_dir, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass
    return path


def add_journal(state, actor, event, detail=None):
    if actor not in ACTORS:
        raise WorkflowValidationError(f"unsupported journal actor: {actor!r}")
    journal = state.setdefault("journal", [])
    journal.append({"seq": len(journal) + 1, "at": utc_now(), "actor": actor,
                    "event": str(event),
                    "detail": None if detail is None else str(detail)})
    return journal[-1]


def record_error(state, stage, kind, message):
    state.setdefault("errors", []).append({
        "at": utc_now(), "stage": str(stage), "kind": str(kind),
        "message": str(message)[:500], "resolved": False})
    state["phase_status"] = "failed"
    return state


def set_blocked(state, reason):
    state["phase_status"] = "blocked"
    state["blocked_reason"] = str(reason)
    return state


def clear_status(state):
    state["phase_status"] = "active"
    state["blocked_reason"] = None
    for error in state.get("errors") or []:
        error["resolved"] = True
    return state


def refresh_phase(state):
    state["phase"] = implied_phase(state)
    return state


def bind_artifact(state, kind, record):
    """Store an accepted artifact with its dependency digest bindings."""
    digests = input_digest_map(state["input"]["identity"],
                               state["input"]["revision_data"])
    deps = ARTIFACT_DEPENDENCIES[kind]
    record["status"] = "accepted"
    record["accepted_at"] = utc_now()
    record["bound_revision"] = state["input"]["revision"]
    record["bound_input_digests"] = {
        key: digests[key] for key in deps["inputs"]}
    record["bound_artifact_digests"] = {
        dep: (state["artifacts"].get(dep) or {}).get("artifact_digest")
        for dep in deps["artifacts"]}
    record["depends_on"] = [*deps["artifacts"], *deps["inputs"]]
    state["artifacts"][kind] = record
    return state


def invalidate_for_revision(state):
    """Mark non-fresh artifacts stale after a revision change (T8)."""
    affected = []
    for kind in ARTIFACT_KINDS:
        entry = state["artifacts"].get(kind) or {}
        if entry.get("status") == "accepted" and not artifact_fresh(state, kind):
            entry["status"] = "stale"
            affected.append(kind)
    return affected


def apply_revision(state, revision_data, reason):
    """T8: bump input revision, cascade stale and recompute the phase."""
    old = state["input"]["revision_data"]
    old_digests = input_digest_map(state["input"]["identity"], old)
    new_digests = input_digest_map(state["input"]["identity"], revision_data)
    changed_inputs = sorted(key for key, value in new_digests.items()
                            if old_digests.get(key) != value)
    state["input"]["revision"] += 1
    state["input"]["revision_data"] = revision_data
    state["input"]["history"].append({
        "revision": state["input"]["revision"],
        "recorded_at": utc_now(),
        "revision_data_sha256": revision_data_digest(revision_data),
        "changed_inputs": changed_inputs,
        "reason": str(reason)})
    affected = invalidate_for_revision(state)
    # Publications are revision data too: a verified PR or TestOps
    # observation for an older head is not evidence for the new one.
    for role, entry in (state["publications"].get("pr") or {}).items():
        if entry.get("status") not in (None, "pending"):
            entry["status"] = "blocked"
            entry["blocked_reason"] = (
                "input revision changed; the PR spec and publication must "
                "be re-verified for the new head")
    refresh_phase(state)
    add_journal(state, "orchestrator", "revision",
                f"revision {state['input']['revision']}: {reason}; "
                f"changed={changed_inputs}; stale={affected}")
    return changed_inputs, affected


def next_intent_id(state):
    numbers = []
    for entry in state.get("intents") or []:
        match = re.fullmatch(r"i-(\d+)", str(entry.get("intent_id") or ""))
        if match:
            numbers.append(int(match.group(1)))
    return f"i-{(max(numbers) + 1) if numbers else 1}"


def new_intent(state, operation, target, argv=None):
    intent = {"intent_id": next_intent_id(state), "operation": operation,
              "target": dict(target),
              "argv_digest": canonical_digest(list(argv)) if argv else None,
              "bound_revision": state["input"]["revision"],
              "declared_at": utc_now(), "dispatched_at": None,
              "status": "declared", "finished_at": None, "evidence": None}
    state.setdefault("intents", []).append(intent)
    return intent


def find_intent(state, intent_id):
    for entry in state.get("intents") or []:
        if entry.get("intent_id") == intent_id:
            return entry
    return None


def unfinished_intents(state):
    return [entry for entry in state.get("intents") or []
            if entry.get("status") in UNFINISHED_INTENT_STATUSES]


def set_intent(intent, status, evidence=None):
    _require(status in INTENT_STATUSES,
             f"intent status unsupported: {status!r}")
    intent["status"] = status
    if status in ("completed", "failed", "unknown"):
        intent["finished_at"] = utc_now()
    if evidence is not None:
        intent["evidence"] = evidence
    return intent
