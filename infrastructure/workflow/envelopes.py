"""Versioned JSON envelopes that bind human/LLM artifacts to digests.

A Markdown or JSON artifact is never trusted as-is: ``accept`` consumes a
strict envelope declaring the document path + sha256, an actor and a
machine-checkable payload (context source digests, scenario coverage,
review decision + frozen scenarios digest, implementation test files,
bindings mapping). Every field is validated before the artifact record is
bound to the current revision's input digests.
"""
import json
from pathlib import Path
import re

from . import state as state_mod

ENVELOPE_VERSION = 1
ENVELOPE_KEYS = {"envelope_version", "artifact", "version", "actor",
                 "document", "payload"}
SCENARIO_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
BINDING_SOURCES = ("assign", "resolve", "imported")


class EnvelopeError(state_mod.WorkflowValidationError):
    """An accepted envelope fails strict validation."""


def _fail(message):
    raise EnvelopeError(message)


def _require(condition, message):
    if not condition:
        _fail(message)


def _expect_keys(obj, required, optional, where):
    _require(isinstance(obj, dict), f"{where} must be an object")
    keys = set(obj)
    missing = required - keys
    _require(not missing, f"{where} missing keys: {sorted(missing)}")
    unknown = keys - required - optional
    _require(not unknown, f"{where} unexpected keys: {sorted(unknown)}")


def _expect_str(value, field):
    _require(isinstance(value, str) and value, f"{field} must be a non-empty string")
    return value


def load_envelope(path):
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        _fail(f"envelope unreadable: {path}: {error}")
    except ValueError as error:
        raise EnvelopeError(
            f"envelope is not valid JSON: {path}") from error
    return validate_envelope(data)


def validate_envelope(data):
    _expect_keys(data, required={"envelope_version", "artifact", "actor",
                                 "payload"},
                 optional={"version", "document"}, where="envelope")
    _require(data["envelope_version"] == ENVELOPE_VERSION,
             f"unsupported envelope_version: {data['envelope_version']!r}")
    kind = data["artifact"]
    _require(kind in state_mod.ARTIFACT_KINDS,
             f"unsupported artifact kind: {kind!r}")
    _require(data["actor"] in state_mod.ACTORS,
             f"unsupported actor: {data['actor']!r}")
    if data.get("version") is not None:
        _expect_str(data["version"], "envelope.version")
    document = data.get("document")
    if kind != "bindings":
        _require(document is not None,
                 f"{kind} envelope requires a document")
    if document is not None:
        _expect_keys(document, required={"path", "sha256"}, optional=set(),
                     where="envelope.document")
        _expect_str(document["path"], "document.path")
        state_mod.require_hex64(document["sha256"], "document.sha256")
    payload = data["payload"]
    if kind == "context":
        _validate_context_payload(payload)
    elif kind == "scenarios":
        _validate_scenarios_payload(payload)
    elif kind == "review":
        _validate_review_payload(payload)
    elif kind == "implementation":
        _validate_implementation_payload(payload)
    elif kind == "bindings":
        _validate_bindings_payload(payload)
    return data


def _validate_context_payload(payload):
    _expect_keys(payload, required={"sources"}, optional=set(),
                 where="context.payload")
    sources = payload["sources"]
    _require(isinstance(sources, list) and sources,
             "context.payload.sources must be a non-empty list")
    seen = set()
    for entry in sources:
        _expect_keys(entry, required={"path", "sha256"},
                     optional={"git_blob", "line_count", "purpose",
                               "source_url"},
                     where="context.payload.sources[]")
        _expect_str(entry["path"], "context source path")
        _require(not Path(entry["path"]).is_absolute()
                 and ".." not in Path(entry["path"]).parts,
                 f"context source path must be repo-relative: {entry['path']}")
        state_mod.require_hex64(entry["sha256"], "context source sha256")
        if entry.get("git_blob") is not None:
            _require(isinstance(entry["git_blob"], str)
                     and re.fullmatch(r"[0-9a-f]{40}", entry["git_blob"]),
                     "context source git_blob must be a 40-hex blob id")
        _require(entry["path"] not in seen,
                 f"duplicate context source: {entry['path']}")
        seen.add(entry["path"])


def _validate_scenarios_payload(payload):
    _expect_keys(payload, required={"scenario_ids", "requirement_coverage"},
                 optional=set(), where="scenarios.payload")
    ids = payload["scenario_ids"]
    _require(isinstance(ids, list) and ids, "scenario_ids must be non-empty")
    _require(len(set(ids)) == len(ids), "scenario_ids must be unique")
    for sid in ids:
        _require(isinstance(sid, str) and SCENARIO_ID_RE.fullmatch(sid),
                 f"invalid scenario id: {sid!r}")
    coverage = payload["requirement_coverage"]
    _require(isinstance(coverage, dict) and coverage,
             "requirement_coverage must be a non-empty object")
    for requirement, scenarios in coverage.items():
        _expect_str(requirement, "requirement id")
        _require(isinstance(scenarios, list) and scenarios,
                 f"coverage for {requirement} must be a non-empty list")
        for sid in scenarios:
            _require(sid in ids,
                     f"coverage references undeclared scenario: {sid!r}")


def _validate_review_payload(payload):
    _expect_keys(payload, required={"decision", "scenarios_sha256"},
                 optional=set(), where="review.payload")
    _require(payload["decision"] in state_mod.REVIEW_DECISIONS,
             f"unsupported review decision: {payload['decision']!r}")
    state_mod.require_hex64(payload["scenarios_sha256"],
                            "review.payload.scenarios_sha256")


def _validate_implementation_payload(payload):
    _expect_keys(payload, required={"test_files"}, optional=set(),
                 where="implementation.payload")
    files = payload["test_files"]
    _require(isinstance(files, list) and files,
             "implementation.payload.test_files must be a non-empty list")
    for relpath in files:
        _require(isinstance(relpath, str)
                 and relpath.startswith("tests/")
                 and not Path(relpath).is_absolute()
                 and ".." not in Path(relpath).parts,
                 f"test file must be a repo-relative tests/ path: {relpath!r}")


def _validate_bindings_payload(payload):
    _expect_keys(payload, required={"mapping", "source"}, optional=set(),
                 where="bindings.payload")
    _require(payload["source"] in BINDING_SOURCES,
             f"unsupported bindings source: {payload['source']!r}")
    mapping = payload["mapping"]
    _require(isinstance(mapping, dict) and mapping,
             "bindings.payload.mapping must be a non-empty object")
    seen = set()
    for sid, testops_id in mapping.items():
        _require(isinstance(sid, str) and SCENARIO_ID_RE.fullmatch(sid),
                 f"invalid scenario id in bindings: {sid!r}")
        _require(isinstance(testops_id, int)
                 and not isinstance(testops_id, bool) and testops_id > 0,
                 f"TestOps ID must be a positive int: {testops_id!r}")
        _require(testops_id not in seen,
                 f"TestOps ID {testops_id} bound to more than one scenario")
        seen.add(testops_id)


def verify_document(root, document):
    """The declared document must exist with the declared sha256."""
    path = (Path(root) / document["path"]).resolve()
    try:
        path.relative_to(Path(root).resolve())
    except ValueError:
        _fail(f"document escapes the repository: {document['path']}")
    _require(path.is_file(), f"document missing: {document['path']}")
    actual = state_mod.sha256_file(path)
    _require(actual == document["sha256"].lower(),
             f"document digest mismatch for {document['path']}")
    return actual


def artifact_digest(kind, document_sha256, payload):
    return state_mod.canonical_digest(
        {"artifact": kind, "document_sha256": document_sha256,
         "payload": payload})


def validate_context_sources(git, sources):
    """Recompute every declared context source against the app checkout."""
    problems = []
    for entry in sources:
        relpath = entry["path"]
        actual_sha = git.file_sha256(relpath)
        if actual_sha is None:
            problems.append(f"{relpath}: missing in the app checkout")
            continue
        if actual_sha != entry["sha256"].lower():
            problems.append(f"{relpath}: sha256 mismatch")
        if entry.get("git_blob") is not None:
            actual_blob = git.git_blob(relpath)
            if actual_blob != entry["git_blob"]:
                problems.append(f"{relpath}: git blob mismatch")
    return problems


def validate_scenarios(payload, requirement_ids):
    """Scenario IDs unique + every requirement covered at least once."""
    ids = payload["scenario_ids"]
    coverage = payload["requirement_coverage"]
    problems = []
    for requirement in requirement_ids:
        if requirement not in coverage:
            problems.append(f"requirement {requirement} has no scenario coverage")
    for requirement in coverage:
        if requirement not in requirement_ids:
            problems.append(f"coverage references unknown requirement "
                            f"{requirement}")
    covered = {sid for scenarios in coverage.values() for sid in scenarios}
    for sid in ids:
        if sid not in covered:
            problems.append(f"scenario {sid} is not mapped to any requirement")
    return problems


def validate_bindings(payload, scenario_ids):
    mapping = payload["mapping"]
    problems = []
    for sid in mapping:
        if sid not in scenario_ids:
            problems.append(f"bindings reference unknown scenario {sid}")
    for sid in scenario_ids:
        if sid not in mapping:
            problems.append(f"scenario {sid} has no TestOps binding")
    return problems
