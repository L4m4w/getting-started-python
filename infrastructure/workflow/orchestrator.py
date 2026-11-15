"""Minimal QA workflow orchestrator

Sequential executor of the fixed MVP stage chain with persisted state,
resume and duplicate protection. External effects are always mediated:
delegated CLIs run through the injected runner, TestOps upload lifecycle
lives only in the per-execution ``state.json``, and PR publication goes
through an injected transport (none is shipped for the offline stage).
"""
from contextlib import contextmanager
import hashlib
import os
from pathlib import Path
import re

from infrastructure.reporting.testops import lifecycle as tlifecycle
from infrastructure.reporting.testops import results as tresults
from infrastructure.reporting.testops import state as tstate

from . import (adapters, contracts, envelopes, index as index_mod,
               state as state_mod)
from .locks import WorkflowLock
from .state import (WorkflowBlockedError, WorkflowError,
                    WorkflowLaunchError, WorkflowPermissionError,
                    WorkflowValidationError)

EXIT_OK = 0
EXIT_BLOCKED = 69
EXIT_UNKNOWN = 75
EXIT_PERMISSION = 77
EXIT_LAUNCH_ERROR = 127
EXIT_INTERRUPTED = 130

REQUIREMENT_ID_RE = re.compile(r"\bR\d+\b")

# Pilot policy (wave 19): required head/fix execution is six passed on the
# API scope; the strength gate is a separate required evidence gate that an
# imported accepted red baseline (4 expected failures) may satisfy.
DEFAULT_EXPECTED_EXECUTIONS = [
    {"variant": "head", "required": True, "scope": "api",
     "expect": {"total": 6, "passed": 6, "failed": 0, "errors": 0}},
]
DEFAULT_STRENGTH_EVIDENCE = {
    "variant": "base", "required": True, "scope": "api",
    "expect": {"total": 4, "failed": 4},
}

PR_ROLES = ("app", "tests")


def _requirement_ids_from(path):
    ids = []
    for token in REQUIREMENT_ID_RE.findall(path.read_text(encoding="utf-8")):
        if token not in ids:
            ids.append(token)
    return ids


def _node_id_covers(scenario_id, node_id):
    """Boundary-token containment: UNIT-VAL-0010 must not cover 001."""
    pattern = (r"(?<![A-Za-z0-9_-])" + re.escape(scenario_id)
               + r"(?![A-Za-z0-9_-])")
    return re.search(pattern, node_id) is not None


class Orchestrator:
    """One orchestrator per project root; stores under ``<root>/artifacts``.

    ``runner`` executes delegated argv (default: real subprocesses; fakes
    in tests). ``pr_transports`` maps repo role ("app"/"tests" or "*") to a
    :class:`adapters.PrTransport` implementation; absent means no PR
    transport exists and every PR write is blocked by construction.
    """

    def __init__(self, root, store_dir=None, runner=None,
                 pr_transports=None, git_adapter=None,
                 tests_git_adapter=None, source_contract=None,
                 scenario_contract=None, accepted_provenance=None):
        self.root = Path(root)
        self.store_dir = (Path(store_dir) if store_dir is not None
                          else self.root / "artifacts" / "workflow")
        self.runner = runner or adapters.SubprocessRunner()
        self.pr_transports = dict(pr_transports or {})
        self._git_adapter = git_adapter
        self._tests_git_adapter = tests_git_adapter
        self._source_contract = (source_contract
                                 if source_contract is not None
                                 else contracts.pilot_source_contract())
        self._scenario_contract = (scenario_contract
                                   if scenario_contract is not None
                                   else contracts.pilot_scenario_contract())
        self._accepted_provenance = (
            tuple(accepted_provenance)
            if accepted_provenance is not None
            else contracts.DEFAULT_ACCEPTED_HISTORICAL_BASELINES
        )

    # -- storage helpers ------------------------------------------------

    @staticmethod
    @contextmanager
    def _index_locked(store_dir):
        """IndexLock surfaced as a domain error (exit 69 upstream)."""
        try:
            with index_mod.acquire(store_dir) as lock:
                yield lock
        except tlifecycle.LockHeldError as error:
            raise WorkflowBlockedError(str(error)) from error

    @staticmethod
    @contextmanager
    def _locked(workflow_dir, operation):
        """WorkflowLock surfaced as a domain error (exit 69 upstream)."""
        try:
            with WorkflowLock(workflow_dir, operation=operation):
                yield
        except tlifecycle.LockHeldError as error:
            raise WorkflowBlockedError(str(error)) from error

    def workflow_dir(self, workflow_id):
        return self.store_dir / workflow_id

    def _resolve_workflow_id(self, hint=None):
        if hint:
            return hint
        candidates = sorted(
            entry.name for entry in self.store_dir.iterdir()
            if entry.is_dir() and state_mod.WORKFLOW_ID_RE.fullmatch(entry.name)
            and state_mod.state_path(entry).is_file()
        ) if self.store_dir.is_dir() else []
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise WorkflowBlockedError("no workflow found; run init first")
        raise WorkflowBlockedError(
            f"multiple workflows present; pass --workflow-id: {candidates}")

    def _git(self, state):
        if self._git_adapter is not None:
            return self._git_adapter
        repo_path = (state["input"].get("locals") or {}).get("app_repo_path")
        if not repo_path:
            raise WorkflowBlockedError(
                "input.locals.app_repo_path not recorded; re-run init with "
                "--app-repo-path to enable source re-verification")
        return adapters.GitReadAdapter(repo_path)

    def _tests_root(self, state):
        local = (state["input"].get("locals") or {})
        return Path(local.get("tests_repo_path") or self.root)

    def _tests_git(self, state):
        if self._tests_git_adapter is not None:
            return self._tests_git_adapter
        return adapters.GitReadAdapter(self._tests_root(state))

    @staticmethod
    def _write_payload(workflow_dir, rel_path, data):
        """Atomically persist ``data`` under ``workflow_dir/rel_path``.

        The durable body payload lives inside the workflow dir (never in
        ``artifacts/`` or the project checkout), so a lost body source
        file or an arbitrary current file can never replace what was
        recorded at prepare time.
        """
        path = Path(workflow_dir) / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        with open(temporary, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        return path

    # -- init / update-input ---------------------------------------------

    def init(self, *, pilot_id, app_repo, app_base_sha, app_head_kind,
             app_head_sha256=None, app_head_git_sha=None, tests_commit=None,
             tests_dirty=None, tests_snapshot_sha256=None,
             tests_repo_path=None, requirements_path,
             requirements_version="1", requirement_ids=None,
             app_repo_path=None, supersede=False,
             expected_executions=None, strength_evidence=None):
        if not state_mod.PILOT_ID_RE.fullmatch(pilot_id or ""):
            raise WorkflowValidationError(f"invalid pilot_id: {pilot_id!r}")
        app_base_sha = state_mod.require_git_sha(app_base_sha, "app_base_sha")
        repo_key = state_mod.normalize_repo_key(app_repo)
        req_path = Path(requirements_path)
        if not req_path.is_file():
            req_path = self.root / requirements_path
        if not req_path.is_file():
            raise WorkflowValidationError(
                f"requirements file not found: {requirements_path}")
        requirement_ids = (list(requirement_ids)
                           if requirement_ids else
                           _requirement_ids_from(req_path))
        if not requirement_ids:
            raise WorkflowValidationError(
                "no requirement ids supplied or parseable (R<n>)")
        head = {"kind": app_head_kind, "sha256": None, "git_sha": None}
        if app_head_kind == "commit":
            head["git_sha"] = state_mod.require_git_sha(
                app_head_git_sha, "app_head git_sha")
        elif app_head_kind == "patch":
            head["sha256"] = state_mod.require_hex64(
                app_head_sha256, "app_patch sha256")
        elif app_head_kind != "none":
            raise WorkflowValidationError(
                f"app_head_kind must be commit|patch|none, got "
                f"{app_head_kind!r}")

        tests_root = Path(tests_repo_path) if tests_repo_path else self.root
        tests_git = adapters.GitReadAdapter(tests_root)
        if tests_commit is None:
            tests_commit = tests_git.head_commit()
            if tests_commit is None:
                raise WorkflowValidationError(
                    "tests_commit not given and HEAD unreadable")
        tests_commit = state_mod.require_git_sha(tests_commit, "tests_commit")
        if tests_dirty is None:
            tests_dirty = tests_git.is_dirty()
        if tests_dirty is None:
            tests_dirty = True
        if tests_dirty and tests_snapshot_sha256 is None:
            from tools import harness as harness_mod
            tests_snapshot_sha256 = adapters.snapshot_allowlist(
                tests_root, harness_mod.API_SOURCE_FILES)
        tests_repo = {"commit": tests_commit, "dirty": bool(tests_dirty),
                      "snapshot_sha256": tests_snapshot_sha256}

        revision_data = {
            "app_head": head,
            "tests_repo": tests_repo,
            "requirements": {"path": str(requirements_path),
                             "version": str(requirements_version),
                             "sha256": state_mod.sha256_file(req_path),
                             "ids": list(requirement_ids)},
            "expected_executions": (list(expected_executions)
                                    if expected_executions is not None
                                    else list(DEFAULT_EXPECTED_EXECUTIONS)),
            "strength_evidence": (dict(strength_evidence)
                                  if strength_evidence is not None
                                  else dict(DEFAULT_STRENGTH_EVIDENCE)),
        }

        workflow_id = state_mod.workflow_id_for(
            pilot_id, repo_key, app_base_sha)
        workflow_dir = self.workflow_dir(workflow_id)
        supersedes_id = None

        # Index phase: never held across subprocess or state writes.
        with self._index_locked(self.store_dir):
            index = index_mod.load_index(self.store_dir)
            entry = index_mod.find_entry(index, repo_key, pilot_id)
            if entry is not None:
                recorded_base = entry["base_sha"]
                expected_id = state_mod.workflow_id_for(
                    pilot_id, repo_key, recorded_base)
                if entry["workflow_id"] != expected_id:
                    raise WorkflowBlockedError(
                        f"index entry {entry['workflow_id']} does not match "
                        f"its recorded identity (expected {expected_id}); "
                        "inspect index/state manually")
                if recorded_base != app_base_sha:
                    if not supersede:
                        raise WorkflowBlockedError(
                            f"pilot {pilot_id!r} is already bound to base "
                            f"{recorded_base} ({entry['workflow_id']}); a new "
                            "base requires --supersede")
                    supersedes_id = entry["workflow_id"]
                    index_mod.register(
                        index, repo_key, pilot_id, workflow_id, app_base_sha,
                        status="creating", supersedes=supersedes_id)
                else:
                    workflow_id = entry["workflow_id"]
                    workflow_dir = self.workflow_dir(workflow_id)
                    # A crash between the index register and the state write
                    # must not silently start a parallel lineage: a recorded
                    # superseded list restores the link on recovery.
                    superseded = entry.get("superseded") or []
                    if superseded and entry.get("status") == "creating":
                        supersedes_id = superseded[-1]
            else:
                index_mod.register(index, repo_key, pilot_id, workflow_id,
                                   app_base_sha, status="creating")
            index_mod.save_index(self.store_dir, index)

        inherited = []
        if supersedes_id:
            old = state_mod.load_state(self.workflow_dir(supersedes_id))
            if old is not None:
                inherited = [dict(intent, inherited_from=supersedes_id)
                             for intent in
                             state_mod.unfinished_intents(old)]
                # The parent's own ancestry is part of this lineage:
                # unresolved snapshots keep blocking and resolved ones
                # keep the recorded remote effect they were settled with.
                inherited.extend(
                    dict(entry)
                    for entry in old.get("inherited_intents") or [])
                # A terminal pr.create in the superseded line may still
                # carry a recorded remote PR. It is inherited as an
                # already-resolved snapshot so the new lineage re-proves
                # the known effect by targeted get instead of trusting a
                # fresh search before any new create.
                for intent in old.get("intents") or []:
                    evidence = intent.get("evidence") or {}
                    number = evidence.get("number")
                    if (intent.get("operation") == "pr.create"
                            and intent.get("status")
                            not in state_mod.UNFINISHED_INTENT_STATUSES
                            and isinstance(number, int)
                            and not isinstance(number, bool)):
                        inherited.append(dict(
                            intent, inherited_from=supersedes_id,
                            status="resolved",
                            resolved_in_parent={
                                "parent_status": intent.get("status"),
                                "parent_evidence": evidence,
                                "checked_at": state_mod.utc_now()}))

        with self._locked(workflow_dir, operation="init"):
            state = state_mod.load_state(workflow_dir)
            if state is None:
                state = state_mod.new_state(
                    pilot_id, repo_key, app_base_sha, revision_data,
                    app_repo_path=app_repo_path,
                    tests_repo_path=str(tests_root),
                    supersedes=supersedes_id,
                    inherited_intents=inherited)
                for intent in inherited:
                    if (intent.get("operation") == "pr.create"
                            and intent.get("status")
                            in state_mod.UNFINISHED_INTENT_STATUSES
                            and intent.get("target", {}).get("repo")
                            in PR_ROLES):
                        role = intent["target"]["repo"]
                        state["publications"]["pr"][role].update(
                            status="blocked",
                            blocked_reason=f"superseded workflow has an "
                                           f"unfinished intent "
                                           f"{intent['intent_id']}; reconcile "
                                           "before any create")
                state_mod.save_state(workflow_dir, state)
                outcome = "created"
            else:
                outcome = self._update_input(state, revision_data,
                                             app_repo_path)
                state_mod.save_state(workflow_dir, state)
        with self._index_locked(self.store_dir):
            index = index_mod.load_index(self.store_dir)
            index_mod.mark_active(index, repo_key, pilot_id, workflow_id,
                                  state["input"]["revision"])
            index_mod.save_index(self.store_dir, index)
        return workflow_id, outcome

    def _update_input(self, state, revision_data, app_repo_path):
        """T8/T9: same digests -> resume; new digests -> revision bump."""
        if app_repo_path:
            state["input"].setdefault("locals", {})[
                "app_repo_path"] = app_repo_path
        if (state_mod.revision_data_digest(state["input"]["revision_data"])
                == state_mod.revision_data_digest(revision_data)):
            state_mod.add_journal(state, "orchestrator", "resumed",
                                  f"revision {state['input']['revision']} "
                                  "unchanged")
            state_mod.refresh_phase(state)
            return "resumed"
        state_mod.apply_revision(state, revision_data, "init with new input")
        return "revisioned"

    # -- status / doctor -------------------------------------------------

    def status(self, workflow_id=None):
        workflow_id = self._resolve_workflow_id(workflow_id)
        state = state_mod.load_state(self.workflow_dir(workflow_id))
        return state

    def _preflight(self, state):
        """Recompute recorded digests against live files and checkouts.

        Recorded bound digests never stand in for the files themselves:
        a gate, mutation or external effect must not proceed on a stale
        approval. ``doctor`` reports these problems; mutating operations
        refuse through :meth:`_require_fresh`.
        """
        problems = []
        revision_data = state["input"]["revision_data"]
        requirements = revision_data.get("requirements") or {}
        req_path = self.root / (requirements.get("path") or "")
        if not requirements.get("path") or not req_path.is_file():
            problems.append("requirements document missing: "
                            f"{requirements.get('path')}")
        elif state_mod.sha256_file(req_path) != requirements.get("sha256"):
            problems.append("requirements document digest drifted: "
                            f"{requirements['path']}")
        tests = revision_data.get("tests_repo") or {}
        tests_git = self._tests_git(state)
        live_commit = tests_git.head_commit() if tests_git else None
        if live_commit is None:
            problems.append("tests repo commit cannot be re-verified")
        elif live_commit.lower() != (tests.get("commit") or "").lower():
            problems.append("tests repo commit drifted: "
                            f"{live_commit} != {tests.get('commit')}")
        live_dirty = tests_git.is_dirty() if tests_git else None
        if live_dirty is None:
            problems.append("tests repo dirty state cannot be re-verified")
        elif live_dirty != bool(tests.get("dirty")):
            problems.append("tests repo dirty state drifted")
        snapshot = tests.get("snapshot_sha256")
        if tests.get("dirty") and snapshot:
            from tools import harness as harness_mod
            actual = adapters.snapshot_allowlist(
                self._tests_root(state), harness_mod.API_SOURCE_FILES)
            if actual != snapshot:
                problems.append("tests source snapshot drifted")
        for kind, artifact in state["artifacts"].items():
            if (artifact or {}).get("status") != "accepted":
                continue
            document = artifact.get("document")
            if document:
                path = self.root / document["path"]
                if not path.is_file():
                    problems.append(f"{kind}: document missing "
                                    f"{document['path']}")
                elif state_mod.sha256_file(path) != document["sha256"]:
                    problems.append(f"{kind}: document digest drifted "
                                    f"{document['path']}")
            if kind == "context" and artifact.get("payload"):
                try:
                    problems.extend(envelopes.validate_context_sources(
                        self._git(state), artifact["payload"]["sources"]))
                except WorkflowBlockedError as error:
                    problems.append(f"context: {error}")
            if kind == "implementation":
                for relpath, sha in (artifact.get("test_files_sha256")
                                     or {}).items():
                    path = self.root / relpath
                    if not path.is_file():
                        problems.append(f"implementation: test file missing "
                                        f"{relpath}")
                    elif state_mod.sha256_file(path) != sha:
                        problems.append(f"implementation: test file drifted "
                                        f"{relpath}")
        return problems

    def _require_fresh(self, state):
        problems = self._preflight(state)
        if problems:
            raise WorkflowBlockedError(
                "preflight failed — recorded inputs no longer match the "
                "working tree; re-run init/doctor and re-accept artifacts: "
                + "; ".join(problems))

    def doctor(self, workflow_id=None):
        """Read-only integrity report; a problem list means exit 69."""
        workflow_id = self._resolve_workflow_id(workflow_id)
        workflow_dir = self.workflow_dir(workflow_id)
        problems = []
        state = state_mod.load_state(workflow_dir)
        if state is None:
            problems.append(f"no state.json under {workflow_dir}")
            return problems
        identity = state["input"]["identity"]
        index = index_mod.load_index(self.store_dir)
        entry = index_mod.find_entry(index, identity["app_repo"],
                                     identity["pilot_id"])
        if entry is None:
            problems.append("index has no entry for this lineage")
        elif entry["workflow_id"] != workflow_id:
            problems.append(
                f"index points at {entry['workflow_id']}, not {workflow_id}")
        elif entry.get("status") != "active":
            problems.append(f"index entry status is {entry.get('status')!r}")
        problems.extend(self._preflight(state))
        return problems

    # -- accept -----------------------------------------------------------

    _ACCEPT_PHASES = {
        "context": ("initialized",),
        "scenarios": ("context_ready", "awaiting_review"),
        "review": ("awaiting_review",),
        "implementation": ("approved",),
        "bindings": ("approved", "implementation_ready", "executed"),
    }

    def accept(self, kind, envelope_path, workflow_id=None):
        envelope = envelopes.load_envelope(envelope_path)
        if envelope["artifact"] != kind:
            raise WorkflowValidationError(
                f"envelope declares artifact {envelope['artifact']!r}, "
                f"expected {kind!r}")
        workflow_id = self._resolve_workflow_id(workflow_id)
        workflow_dir = self.workflow_dir(workflow_id)
        with self._locked(workflow_dir, operation=f"accept-{kind}"):
            state = state_mod.load_state(workflow_dir)
            if state is None:
                raise WorkflowBlockedError("no state; run init first")
            self._require_fresh(state)
            claimed = envelopes.artifact_digest(
                kind, (envelope.get("document") or {}).get("sha256"),
                envelope["payload"])
            existing = state["artifacts"].get(kind) or {}
            if (existing.get("status") == "accepted"
                    and existing.get("artifact_digest") == claimed
                    and state_mod.artifact_fresh(state, kind)):
                # Identical still-fresh artifact: a no-op in every later
                # phase, without re-running compile/list or transports.
                # The declared document is still re-verified so drifted or
                # missing content cannot hide behind the envelope digest.
                if envelope.get("document") is not None:
                    envelopes.verify_document(self.root,
                                              envelope["document"])
                state_mod.add_journal(state, "orchestrator", "resume-accept",
                                      f"{kind}: identical digest, no-op")
                state_mod.save_state(workflow_dir, state)
                return "no-op"
            if (kind in ("context", "implementation", "bindings")
                    and existing.get("status") == "accepted"
                    and state_mod.artifact_fresh(state, kind)
                    and existing.get("artifact_digest") != claimed):
                raise WorkflowBlockedError(
                    f"{kind} already accepted with a different digest at "
                    "this revision; a changed artifact requires a new input "
                    "revision (T8)")
            if state["phase"] == "published":
                raise WorkflowBlockedError(
                    "workflow is published; terminal phase accepts only "
                    "a new input revision")
            allowed = self._ACCEPT_PHASES[kind]
            if state["phase"] not in allowed:
                raise WorkflowBlockedError(
                    f"accept {kind} requires phase in {allowed}; current "
                    f"phase is {state['phase']}")
            record = self._build_artifact(state, kind, envelope)
            digest = envelopes.artifact_digest(
                kind, (record.get("document") or {}).get("sha256"),
                envelope["payload"])
            record["artifact_digest"] = digest
            state_mod.bind_artifact(state, kind, record)
            state_mod.clear_status(state)
            if kind == "review" and record["decision"] != "approved":
                state_mod.set_blocked(
                    state, f"review decision is {record['decision']!r}; fix "
                           "scenarios through a new version (T2)")
            state_mod.refresh_phase(state)
            state_mod.add_journal(
                state, record.get("actor") or "orchestrator", "accept",
                f"{kind} accepted digest={digest[:16]}… "
                f"revision={state['input']['revision']}")
            state_mod.save_state(workflow_dir, state)
            return "accepted"

    def _build_artifact(self, state, kind, envelope):
        payload = envelope["payload"]
        record = {"artifact": kind, "version": envelope.get("version"),
                  "actor": envelope["actor"],
                  "payload": payload}
        if envelope.get("document") is not None:
            sha = envelopes.verify_document(self.root, envelope["document"])
            record["document"] = {"path": envelope["document"]["path"],
                                  "sha256": sha}
        if kind == "context":
            problems = envelopes.validate_context_sources(
                self._git(state), payload["sources"])
            if problems:
                raise WorkflowBlockedError(
                    "context sources failed re-verification: "
                    + "; ".join(problems))
        elif kind == "scenarios":
            problems = envelopes.validate_scenarios(
                payload, state["input"]["revision_data"]["requirements"]["ids"])
            if problems:
                raise WorkflowBlockedError(
                    "scenario coverage failed: " + "; ".join(problems))
            record["scenario_ids"] = list(payload["scenario_ids"])
        elif kind == "review":
            record["decision"] = payload["decision"]
            record["scenarios_sha256"] = payload["scenarios_sha256"]
            scenarios = state["artifacts"].get("scenarios") or {}
            frozen = scenarios.get("artifact_digest")
            if payload["scenarios_sha256"] != frozen:
                raise WorkflowBlockedError(
                    f"review binds scenarios digest "
                    f"{payload['scenarios_sha256'][:16]}… but the frozen "
                    f"digest is {str(frozen)[:16]}…; review must approve "
                    "the accepted scenario set")
        elif kind == "implementation":
            record.update(self._check_implementation(state, payload))
        elif kind == "bindings":
            scenario_ids = (state["artifacts"].get("scenarios") or {}
                            ).get("scenario_ids") or []
            problems = envelopes.validate_bindings(payload, scenario_ids)
            if problems:
                raise WorkflowBlockedError(
                    "bindings failed: " + "; ".join(problems))
            candidate_state = dict(state)
            candidate_artifacts = dict(state.get("artifacts") or {})
            candidate_artifacts["bindings"] = {
                "status": "accepted",
                "mapping": dict(payload["mapping"]),
            }
            candidate_state["artifacts"] = candidate_artifacts
            for exec_entry in state.get("executions") or []:
                if exec_entry.get("bound_revision") != state["input"][
                        "revision"]:
                    continue
                ev_dir = Path(exec_entry["evidence_dir"])
                manifest, _ = adapters.read_manifest(ev_dir)
                if manifest is None:
                    continue
                comp_problems = self._composition_problems(
                    candidate_state, manifest, ev_dir)
                if comp_problems:
                    raise WorkflowBlockedError(
                        f"bindings contradict recorded execution "
                        f"{exec_entry['execution_id']}: "
                        + "; ".join(comp_problems))
            record["mapping"] = dict(payload["mapping"])
            record["source"] = payload["source"]
        return record

    def _check_implementation(self, state, payload):
        """Real compile + collection via the delegated harness CLIs."""
        scenario_ids = (state["artifacts"].get("scenarios") or {}
                        ).get("scenario_ids") or []
        test_files = {}
        for relpath in payload["test_files"]:
            path = self.root / relpath
            if not path.is_file():
                raise WorkflowBlockedError(f"test file missing: {relpath}")
            test_files[relpath] = state_mod.sha256_file(path)
        harness = adapters.HarnessAdapter(self.root, self.runner)
        compile_argv = harness.compile_args()
        compile_run = harness.run(compile_argv)
        if compile_run.code != 0:
            raise WorkflowBlockedError(
                f"compile check failed: {' '.join(compile_argv)} exited "
                f"{compile_run.code or compile_run.error}")
        list_argv = harness.list_args()
        list_run = harness.run(list_argv)
        if list_run.code != 0:
            raise WorkflowBlockedError(
                f"collection failed: {' '.join(list_argv)} exited "
                f"{list_run.code or list_run.error}")
        node_ids = adapters.collected_node_ids(list_run.stdout)
        missing = [sid for sid in scenario_ids
                   if not any(_node_id_covers(sid, node)
                              for node in node_ids)]
        if missing:
            raise WorkflowBlockedError(
                f"no collected node IDs cover scenarios: {missing}")
        return {"test_files_sha256": test_files,
                "checks": {
                    "compile": {"argv": compile_argv,
                                "exit_code": compile_run.code,
                                "checked_at": state_mod.utc_now()},
                    "list": {"argv": list_argv,
                             "exit_code": list_run.code,
                             "checked_at": state_mod.utc_now()},
                    "node_ids": node_ids}}

    # -- check (read-only re-verification) --------------------------------

    def check(self, workflow_id=None):
        """Recompute context digests and compile/collection; never saves."""
        workflow_id = self._resolve_workflow_id(workflow_id)
        state = state_mod.load_state(self.workflow_dir(workflow_id))
        if state is None:
            raise WorkflowBlockedError("no state; run init first")
        problems = self.doctor(workflow_id)
        context = state["artifacts"].get("context") or {}
        if context.get("status") == "accepted":
            try:
                problems.extend(envelopes.validate_context_sources(
                    self._git(state), context["payload"]["sources"]))
            except WorkflowBlockedError as error:
                problems.append(str(error))
        harness = adapters.HarnessAdapter(self.root, self.runner)
        compile_run = harness.run(harness.compile_args())
        if compile_run.code != 0:
            problems.append(f"compile exited {compile_run.code}")
        list_run = harness.run(harness.list_args())
        if list_run.code != 0:
            problems.append(f"list exited {list_run.code}")
        return problems

    # -- run-execution -----------------------------------------------------

    def _execution_variants(self, state):
        revision_data = state["input"]["revision_data"]
        variants = {item["variant"] for item in
                    revision_data.get("expected_executions") or []}
        strength = revision_data.get("strength_evidence") or {}
        if strength.get("variant"):
            variants.add(strength["variant"])
        return variants

    def _satisfying_execution(self, state, variant):
        revision = state["input"]["revision"]
        revision_data = state["input"]["revision_data"]
        for req in (revision_data.get("expected_executions") or []):
            if req.get("variant") == variant and req.get("required"):
                if any(state_mod.execution_matches(entry, req, revision)
                       for entry in state["executions"]):
                    return True
        strength = revision_data.get("strength_evidence") or {}
        if strength.get("variant") == variant and strength.get("required"):
            req = {"variant": variant, "expect": strength.get("expect"),
                   "scope": strength.get("scope")}
            if any(state_mod.execution_matches(entry, req, revision)
                   for entry in state["executions"]):
                return True
        return False

    def run_execution(self, variant, workflow_id=None, *, allow_sut=False,
                      rerun=False, app_base_sha=None, app_patch_sha256=None,
                      gateway_image_id=None, gateway_container=None):
        if variant not in state_mod.EXECUTION_VARIANTS:
            raise WorkflowValidationError(f"unknown variant: {variant!r}")
        workflow_id = self._resolve_workflow_id(workflow_id)
        workflow_dir = self.workflow_dir(workflow_id)
        harness = adapters.HarnessAdapter(self.root, self.runner)
        with self._locked(workflow_dir, operation="run-execution"):
            state = state_mod.load_state(workflow_dir)
            if state is None:
                raise WorkflowBlockedError("no state; run init first")
            self._require_fresh(state)
            if state["phase"] not in ("implementation_ready", "executed"):
                raise WorkflowBlockedError(
                    f"run-execution requires phase implementation_ready or "
                    f"executed; current phase is {state['phase']}")
            if variant not in self._execution_variants(state):
                raise WorkflowBlockedError(
                    f"variant {variant!r} is not declared in "
                    "expected_executions/strength_evidence")
            if (not rerun
                    and self._satisfying_execution(state, variant)):
                return {"outcome": "no-op",
                        "detail": f"a satisfying {variant} execution "
                                  "already exists at this revision"}
            open_intent = self._open_run_intent(state, variant)
            if open_intent is not None and open_intent["status"] != "declared":
                raise WorkflowBlockedError(
                    f"intent {open_intent['intent_id']} for {variant} is "
                    f"{open_intent['status']}; run reconcile before any "
                    "new run — an undetermined run is never repeated")
            # Run args are bound to the recorded revision: the caller may
            # not point a run at an unrecorded app head or base, and
            # contradictory values are refused before any dispatch.
            identity = state["input"]["identity"]
            head = state["input"]["revision_data"]["app_head"]
            expected_base = identity["app_base_sha"]
            expected_patch = None
            if variant == "head":
                if head.get("kind") == "patch":
                    expected_patch = head.get("sha256")
                elif head.get("kind") == "commit":
                    expected_base = head.get("git_sha")
                else:
                    raise WorkflowBlockedError(
                        "app_head kind=none has no immutable head to run; "
                        "declare a patch or commit head via init")
            app_base_sha = (app_base_sha or expected_base).lower()
            app_patch_sha256 = ((app_patch_sha256 or expected_patch or "")
                                .lower() or None)
            if (app_base_sha != expected_base.lower()
                    or app_patch_sha256 != expected_patch):
                raise WorkflowBlockedError(
                    f"run args contradict the recorded {variant} identity "
                    f"(expected base {expected_base}, patch "
                    f"{expected_patch}); refused before dispatch")
            argv = harness.api_run_args(
                app_base_sha=app_base_sha, app_patch_sha256=app_patch_sha256,
                gateway_image_id=gateway_image_id,
                gateway_container=gateway_container, allow_sut=allow_sut)
            intent = open_intent or state_mod.new_intent(
                state, "run.execution", {"variant": variant}, argv=argv)
            intent["argv_digest"] = state_mod.canonical_digest(argv)
            intent["status"] = "dispatched"
            intent["dispatched_at"] = state_mod.utc_now()
            state_mod.add_journal(state, "orchestrator", "run-execution",
                                  f"{variant}: intent {intent['intent_id']} "
                                  "dispatched")
            state_mod.save_state(workflow_dir, state)

            def on_evidence(candidate):
                evidence = dict(intent.get("evidence") or {})
                evidence["evidence_dir"] = str(candidate)
                intent["evidence"] = evidence
                state_mod.save_state(workflow_dir, state)

            try:
                outcome, evidence_dir = harness.run_collecting_evidence(
                    argv, on_evidence)
            except KeyboardInterrupt:
                return self._runner_failure(
                    state, workflow_dir, intent,
                    "interrupted during delegated run", "interrupted",
                    EXIT_INTERRUPTED)
            except Exception as error:
                return self._runner_failure(
                    state, workflow_dir, intent,
                    f"runner raised {type(error).__name__}: {error}",
                    "unknown", EXIT_UNKNOWN)
            return self._finish_run(state, workflow_dir, intent, outcome,
                                    evidence_dir)

    @staticmethod
    def _runner_failure(state, workflow_dir, intent, detail, outcome, code):
        """Persist the intent as undetermined before reporting a crash."""
        state_mod.set_intent(intent, "unknown",
                             {"exit_code": None, "detail": detail})
        state_mod.record_error(state, "run_execution", outcome, detail)
        state_mod.save_state(workflow_dir, state)
        return {"outcome": outcome, "exit": code}

    def _open_run_intent(self, state, variant):
        revision = state["input"]["revision"]
        for intent in state.get("intents") or []:
            if (intent.get("operation") == "run.execution"
                    and intent.get("target", {}).get("variant") == variant
                    and intent.get("bound_revision") == revision
                    and intent.get("status")
                    in state_mod.UNFINISHED_INTENT_STATUSES):
                return intent
        return None

    def _finish_run(self, state, workflow_dir, intent, outcome, evidence_dir):
        if outcome.error == "interrupted":
            state_mod.set_intent(intent, "unknown",
                                 {"exit_code": None,
                                  "detail": "run interrupted; outcome "
                                            "undetermined"})
            state_mod.record_error(state, "run_execution", "interrupted",
                                   "delegated run interrupted")
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "interrupted", "exit": EXIT_INTERRUPTED}
        if outcome.error == "timeout":
            state_mod.set_intent(intent, "unknown",
                                 {"exit_code": None,
                                  "detail": "run timed out; outcome "
                                            "undetermined"})
            state_mod.record_error(state, "run_execution", "timeout",
                                   "delegated run timed out")
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "unknown", "exit": EXIT_UNKNOWN}
        if outcome.error == "launch_error":
            state_mod.set_intent(intent, "failed",
                                 {"exit_code": None,
                                  "detail": "delegated command could not "
                                            "start; nothing ran"})
            state_mod.add_journal(state, "orchestrator", "run-execution",
                                  f"{intent['intent_id']} launch_error")
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "launch_error", "exit": EXIT_LAUNCH_ERROR}
        if evidence_dir is None:
            # The harness prints its evidence dir before pytest starts, so
            # an exited process without a link provably never ran tests.
            state_mod.set_intent(intent, "failed",
                                 {"exit_code": outcome.code,
                                  "detail": "no evidence link; the delegated "
                                            "run provably never launched "
                                            "pytest"})
            state_mod.record_error(state, "run_execution", "no_evidence",
                                   f"delegated run exited {outcome.code} "
                                   "before producing evidence")
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "failed", "exit": outcome.code or EXIT_BLOCKED}
        return self._adopt_run_evidence(state, workflow_dir, intent,
                                        evidence_dir, outcome.code)

    def _adopt_run_evidence(self, state, workflow_dir, intent, evidence_dir,
                            exit_code, source="orchestrated"):
        try:
            manifest, manifest_sha = adapters.read_manifest(evidence_dir)
        except WorkflowValidationError as error:
            state_mod.set_intent(intent, "unknown",
                                 {"exit_code": exit_code,
                                  "detail": f"manifest unreadable: {error}"})
            state_mod.record_error(state, "run_execution",
                                   "manifest_corrupt", str(evidence_dir))
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "unknown", "exit": EXIT_UNKNOWN}
        if manifest is None:
            state_mod.set_intent(intent, "unknown",
                                 {"exit_code": exit_code,
                                  "detail": "manifest.json missing in "
                                            "evidence dir"})
            state_mod.record_error(state, "run_execution",
                                   "manifest_missing", str(evidence_dir))
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "unknown", "exit": EXIT_UNKNOWN}
        recounted = adapters.junit_summary(Path(evidence_dir) / "junit.xml")
        if manifest.get("status") != "completed" or recounted is None:
            state_mod.set_intent(intent, "unknown",
                                 {"exit_code": exit_code,
                                  "detail": "manifest not completed or junit "
                                            "unreadable"})
            state_mod.record_error(state, "run_execution",
                                   "incomplete_evidence", str(evidence_dir))
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "unknown", "exit": EXIT_UNKNOWN}
        if recounted != manifest.get("junit_summary"):
            state_mod.set_intent(intent, "unknown",
                                 {"exit_code": exit_code,
                                  "detail": "manifest junit_summary does not "
                                            "match junit.xml"})
            state_mod.record_error(state, "run_execution",
                                   "evidence_mismatch", str(evidence_dir))
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "unknown", "exit": EXIT_UNKNOWN}
        execution_id = Path(evidence_dir).name
        problems = self._manifest_problems(
            state, manifest, Path(evidence_dir),
            manifest_sha256=manifest_sha)
        if problems:
            state_mod.set_intent(
                intent, "failed",
                {"exit_code": exit_code,
                 "detail": "evidence identity rejected: "
                           + "; ".join(problems)})
            state_mod.record_error(state, "run_execution",
                                   "identity_mismatch",
                                   str(evidence_dir))
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "failed", "exit": EXIT_BLOCKED,
                    "detail": "evidence does not match the recorded "
                              "revision identity"}
        if not any(entry["execution_id"] == execution_id
                   for entry in state["executions"]):
            variant = (self._manifest_variant(
                           manifest, state["input"]["identity"],
                           state["input"]["revision_data"])
                       or intent["target"].get("variant"))
            bound = (state["input"]["revision"]
                     if self._manifest_matches_revision(
                         manifest, state["input"]["identity"],
                         state["input"]["revision_data"]) else 0)
            state["executions"].append({
                "execution_id": execution_id,
                "variant": variant,
                "bound_revision": bound,
                "source": source,
                "evidence_dir": str(evidence_dir),
                "manifest_sha256": manifest_sha,
                "junit_summary": recounted,
                "exit_code": manifest.get("exit_code"),
                "status": "completed",
                "selection": manifest.get("selection"),
                "recorded_at": state_mod.utc_now(),
                "testops_state_dir": str(
                    self.root / "artifacts" / "testops" / execution_id)})
        state_mod.set_intent(intent, "completed",
                             {"exit_code": exit_code,
                              "outcome": "run_completed",
                              "evidence_dir": str(evidence_dir),
                              "execution_id": execution_id})
        state_mod.clear_status(state)
        state_mod.refresh_phase(state)
        state_mod.add_journal(state, "orchestrator", "execution",
                              f"{execution_id} recorded "
                              f"(variant={state['executions'][-1]['variant']}, "
                              f"exit={manifest.get('exit_code')})")
        state_mod.save_state(workflow_dir, state)
        return {"outcome": "recorded", "execution_id": execution_id,
                "exit": EXIT_OK}

    @staticmethod
    def _manifest_variant(manifest, identity=None, revision_data=None):
        """Variant of the run relative to the recorded identity/head.

        A declared patch is always head evidence. A bare declared
        ``app_base_sha`` is classified base only when it is proven equal to
        the workflow base, and head when it equals the recorded commit
        head (kind=commit runs report the head SHA through the same flag).
        Without a revision context a bare declared SHA can never be proven
        to be the base, so it is conservatively classified head — the
        evidence then still has to prove the exact head in
        :meth:`_manifest_matches_revision`.
        """
        declared = ((manifest.get("environment") or {})
                    .get("declared") or {})
        base = (declared.get("app_base_sha") or "").lower()
        if declared.get("app_patch_sha256"):
            return "head"
        if not base:
            return None
        head = (revision_data or {}).get("app_head") or {}
        git_sha = (head.get("git_sha") or "").lower()
        if head.get("kind") == "commit" and base == git_sha:
            return "head"
        if identity is None and revision_data is None:
            return "head"
        return "base"

    @staticmethod
    def _manifest_matches_revision(manifest, identity, revision_data):
        """Whether the declared environment belongs to the live revision.

        A base run is bound by the immutable ``identity.app_base_sha`` — it
        is evidence for every revision that shares that base. A patch head
        run must match base AND patch; a commit head run must match the
        exact head SHA (a base SHA is never passed off as head).
        """
        declared = ((manifest.get("environment") or {})
                    .get("declared") or {})
        variant = Orchestrator._manifest_variant(
            manifest, identity, revision_data)
        base = (declared.get("app_base_sha") or "").lower()
        patch = (declared.get("app_patch_sha256") or "").lower()
        head = revision_data.get("app_head") or {}
        if variant == "base":
            return bool(base) \
                and base == (identity.get("app_base_sha") or "").lower()
        if variant == "head" and head.get("kind") == "patch":
            return (base == (identity.get("app_base_sha") or "").lower()
                    and bool(patch)
                    and patch == (head.get("sha256") or "").lower())
        if variant == "head" and head.get("kind") == "commit":
            return bool(base) \
                and base == (head.get("git_sha") or "").lower() and not patch
        return False

    def _manifest_problems(self, state, manifest, evidence_dir,
                           provenance=None, *, manifest_sha256=None,
                           testops_state=None):
        """Strict identity of imported/adopted evidence (F2 + R1 + R3)."""
        problems = []
        evidence_dir = Path(evidence_dir)
        execution_id = evidence_dir.name
        revision_data = state["input"]["revision_data"]
        identity = state["input"]["identity"]
        tests = revision_data.get("tests_repo") or {}
        if manifest.get("run_id") != execution_id:
            problems.append(
                f"manifest run_id {manifest.get('run_id')!r} does not match "
                f"evidence dir {execution_id!r}")
        targets = ((manifest.get("selection") or {}).get("targets") or [])
        if not any(t == "tests/api" or t.startswith("tests/api/")
                   for t in targets):
            problems.append(
                f"manifest selection targets {targets!r} do not run "
                "the required tests/api scope")
        variant = self._manifest_variant(manifest, identity, revision_data)
        if variant is None:
            problems.append("manifest declares no usable app identity")
            return problems
        if not self._manifest_matches_revision(
                manifest, identity, revision_data):
            problems.append(
                f"manifest {variant} environment does not match the "
                "recorded revision (base+patch or head SHA)")

        allowed_historical_files = None
        if provenance is not None:
            if manifest_sha256 is None:
                manifest_path = evidence_dir / "manifest.json"
                if manifest_path.is_file():
                    manifest_sha256 = state_mod.sha256_file(manifest_path)
            allowed_historical_files, prov_problems = (
                contracts.verify_historical_baseline_acceptance(
                    provenance,
                    accepted_records=self._accepted_provenance,
                    source_contract=self._source_contract,
                    state=state,
                    execution_id=execution_id,
                    variant=variant,
                    manifest=manifest,
                    manifest_sha256=manifest_sha256,
                    evidence_dir=evidence_dir,
                    root=self.root,
                ))
            if prov_problems:
                problems.extend(prov_problems)
                return problems
            expected_commit = provenance["tests_repo"]["commit"].lower()
            expected_dirty = bool(provenance["tests_repo"]["dirty"])
        else:
            expected_commit = (tests.get("commit") or "").lower()
            expected_dirty = bool(tests.get("dirty"))

        repo = manifest.get("repository") or {}
        if (repo.get("commit") or "").lower() != expected_commit:
            problems.append(
                f"manifest tests commit {repo.get('commit')!r} != "
                f"{expected_commit!r}")
        if bool(repo.get("dirty")) != expected_dirty:
            problems.append("manifest tests dirty flag mismatch")

        problems.extend(self._source_identity_problems(
            state, manifest, evidence_dir,
            allowed_historical_files=allowed_historical_files))
        problems.extend(self._environment_problems(variant, manifest))
        problems.extend(self._composition_problems(
            state, manifest, evidence_dir, testops_state=testops_state))
        return problems

    def _source_identity_problems(self, state, manifest, evidence_dir,
                                  *, allowed_historical_files=None):
        return contracts.validate_source_identity(
            self._source_contract, state, manifest, Path(evidence_dir),
            self._tests_git(state), self._tests_root(state),
            allowed_historical_files=allowed_historical_files)

    @staticmethod
    def _environment_problems(variant, manifest):
        problems = []
        environment = manifest.get("environment")
        if not isinstance(environment, dict):
            return ["manifest has no environment block"]
        declared = environment.get("declared") or {}
        check = environment.get("container_check") or {}
        wants_binding = bool(declared.get("gateway_image_id")
                             or declared.get("gateway_container"))
        if variant == "head" or wants_binding:
            if wants_binding and not check.get("performed"):
                problems.append("container_check was not performed although "
                                "an image/container binding was declared")
            if check.get("performed"):
                if not check.get("container_running"):
                    problems.append("bound gateway container was not running")
                if declared.get("gateway_image_id") and not \
                        check.get("matches_declared_image"):
                    problems.append("bound container image does not match "
                                    "the declared gateway image")
                if (declared.get("gateway_container")
                        and check.get("container_name")
                        != declared["gateway_container"]):
                    problems.append("bound container name does not match "
                                    "the declared gateway container")
        return problems

    def _composition_problems(self, state, manifest, evidence_dir,
                              testops_state=None):
        """Exact scenario composition of JUnit and raw Allure evidence."""
        identity = ((state.get("input") or {}).get("identity"))
        revision_data = ((state.get("input") or {}).get("revision_data"))
        variant = self._manifest_variant(manifest, identity, revision_data)
        return contracts.validate_scenario_composition(
            self._scenario_contract, variant, state, manifest,
            Path(evidence_dir), testops_state=testops_state)

    # -- import-execution ---------------------------------------------------

    def import_execution(self, execution_id, workflow_id=None,
                         provenance=None):
        """Read-only adoption of existing run/TestOps evidence.

        ``provenance`` is permitted only for ``variant == "base"`` and must
        be a versioned ``historical_baseline_acceptance`` record matching an
        authoritative coordinator-accepted baseline record, concrete review
        decisions on disk and exact manifest/junit/allure/source digests.
        """
        if not state_mod.EXECUTION_ID_RE.fullmatch(execution_id or ""):
            raise WorkflowValidationError(
                f"invalid execution id: {execution_id!r}")
        if provenance is not None and not isinstance(provenance, dict):
            raise WorkflowValidationError(
                "provenance must be a versioned JSON object")
        workflow_id = self._resolve_workflow_id(workflow_id)
        workflow_dir = self.workflow_dir(workflow_id)
        adapter = adapters.TestOpsAdapter(self.root, self.runner)
        with self._locked(workflow_dir, operation="import-execution"):
            state = state_mod.load_state(workflow_dir)
            if state is None:
                raise WorkflowBlockedError("no state; run init first")
            if state["phase"] not in ("implementation_ready", "executed"):
                raise WorkflowBlockedError(
                    f"import-execution requires phase implementation_ready "
                    f"or executed; current phase is {state['phase']}")
            entry = next((item for item in state["executions"]
                          if item["execution_id"] == execution_id), None)
            if entry is not None:
                return self._reimport_recorded_execution(
                    state, workflow_dir, adapter, entry, provenance)
            evidence_dir = self.root / "artifacts" / "harness" / execution_id
            manifest, manifest_sha = adapters.read_manifest(evidence_dir)
            if manifest is None or manifest.get("status") != "completed":
                raise WorkflowBlockedError(
                    f"no completed harness manifest for {execution_id}")
            recounted = adapters.junit_summary(evidence_dir / "junit.xml")
            if recounted is None or recounted != manifest.get("junit_summary"):
                raise WorkflowBlockedError(
                    f"junit evidence for {execution_id} is unreadable or "
                    "inconsistent with the manifest")
            try:
                testops_state = adapter.read_execution_state(execution_id)
            except tstate.StateCorruptError as error:
                raise WorkflowBlockedError(
                    f"TestOps state for {execution_id} is corrupt: "
                    f"{error}") from error
            self._verify_testops_source(adapter, execution_id, testops_state)
            try:
                self._require_fresh(state)
            except WorkflowBlockedError as error:
                return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                        "detail": str(error)}
            identity = state["input"]["identity"]
            revision_data = state["input"]["revision_data"]
            variant = self._manifest_variant(manifest, identity,
                                             revision_data)
            if variant is None or variant not in self._execution_variants(
                    state):
                return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                        "detail": f"manifest for {execution_id} declares no "
                                  "usable app identity or an undeclared "
                                  f"variant ({variant!r})"}
            problems = self._manifest_problems(
                state, manifest, evidence_dir, provenance=provenance,
                manifest_sha256=manifest_sha, testops_state=testops_state)
            if problems:
                return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                        "detail": "evidence identity rejected: "
                                  + "; ".join(problems),
                        "problems": problems}
            bound = (state["input"]["revision"]
                     if self._manifest_matches_revision(
                         manifest, identity, revision_data) else 0)
            intent = state_mod.new_intent(
                state, "run.execution",
                {"variant": variant, "import": True})
            execution = {
                "execution_id": execution_id,
                "variant": variant,
                "bound_revision": bound,
                "source": "imported",
                "evidence_dir": str(evidence_dir),
                "manifest_sha256": manifest_sha,
                "junit_summary": recounted,
                "exit_code": manifest.get("exit_code"),
                "status": "completed",
                "selection": manifest.get("selection"),
                "recorded_at": state_mod.utc_now(),
                "testops_state_dir": str(adapter.state_dir(execution_id))}
            if provenance is not None:
                execution["provenance"] = provenance
            state["executions"].append(execution)
            state_mod.set_intent(intent, "completed",
                                 {"outcome": "imported",
                                  "execution_id": execution_id})
            self._observe_testops(state, adapter, execution_id,
                                  variant=variant)
            state_mod.clear_status(state)
            state_mod.refresh_phase(state)
            state_mod.add_journal(state, "orchestrator", "import-execution",
                                  f"{execution_id} imported "
                                  f"(variant={execution['variant']}, "
                                  f"bound_revision={bound})")
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "imported", "execution_id": execution_id,
                    "variant": execution["variant"],
                    "bound_revision": bound}

    def _reimport_recorded_execution(self, state, workflow_dir, adapter,
                                     entry, provenance):
        """Re-import of an already recorded execution id.

        An entry bound to the current revision is an honest no-op. Head
        evidence of a past revision is never reused: a changed head
        requires a new head run — only a base execution may be re-bound
        to the current revision, and only after the same full live
        verification a fresh import performs (manifest, junit recount,
        source/scenario/provenance/environment identity and preflight).
        The rebind is journaled as audit; evidence and history are never
        rewritten, and a repeat after a successful bind is a no-op.
        """
        execution_id = entry["execution_id"]
        revision = state["input"]["revision"]
        if entry.get("bound_revision") == revision:
            return {"outcome": "no-op",
                    "detail": "execution already recorded at this "
                              "revision"}
        if entry.get("variant") != "base":
            return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                    "detail": f"{execution_id} is "
                              f"{entry.get('variant')!r} evidence bound to "
                              f"revision {entry.get('bound_revision')}; "
                              "head evidence of a past revision is never "
                              "reused — record a new head execution"}
        if (provenance is not None
                and entry.get("provenance") is not None
                and provenance != entry["provenance"]):
            return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                    "detail": "re-import provenance contradicts the "
                              "recorded acceptance record"}
        provenance = (provenance if provenance is not None
                      else entry.get("provenance"))
        evidence_dir = Path(entry["evidence_dir"])
        try:
            manifest, manifest_sha = adapters.read_manifest(evidence_dir)
        except WorkflowValidationError as error:
            return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                    "detail": f"manifest unreadable: {error}"}
        if manifest is None or manifest.get("status") != "completed":
            return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                    "detail": f"no completed harness manifest for "
                              f"{execution_id}; the recorded base stays "
                              "bound to its revision"}
        recounted = adapters.junit_summary(evidence_dir / "junit.xml")
        if recounted is None or recounted != manifest.get("junit_summary"):
            return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                    "detail": "junit evidence unreadable or inconsistent "
                              "with the manifest"}
        try:
            testops_state = adapter.read_execution_state(execution_id)
        except tstate.StateCorruptError as error:
            return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                    "detail": f"TestOps state for {execution_id} is "
                              f"corrupt: {error}"}
        try:
            self._verify_testops_source(adapter, execution_id,
                                        testops_state)
            self._require_fresh(state)
        except WorkflowBlockedError as error:
            return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                    "detail": str(error)}
        problems = self._manifest_problems(
            state, manifest, evidence_dir, provenance=provenance,
            manifest_sha256=manifest_sha, testops_state=testops_state)
        if problems:
            return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                    "detail": "evidence identity rejected: "
                              + "; ".join(problems),
                    "problems": problems}
        previous = entry.get("bound_revision")
        entry["bound_revision"] = revision
        entry["rebound_at"] = state_mod.utc_now()
        entry["rebound_from_revision"] = previous
        state_mod.clear_status(state)
        state_mod.refresh_phase(state)
        state_mod.add_journal(
            state, "orchestrator", "base-rebind",
            f"{execution_id} rebound to revision {revision} "
            f"(from {previous}) after full evidence re-verification")
        state_mod.save_state(workflow_dir, state)
        return {"outcome": "rebound", "execution_id": execution_id,
                "bound_revision": revision}

    def _verify_testops_source(self, adapter, execution_id,
                               testops_state=None):
        """Exact integrity check of an uploaded execution before import."""
        if testops_state is None:
            testops_state = adapter.read_execution_state(execution_id)
        if testops_state is None:
            return
        upload = testops_state.get("upload") or {}
        if upload.get("status") != "uploaded":
            return
        package = testops_state.get("package") or {}
        source = testops_state.get("results") or {}
        try:
            source_path = Path(source["path"])
            if not source_path.is_absolute():
                source_path = self.root / source_path
            pkg_dir = Path(package["dir"])
            if not pkg_dir.is_absolute():
                pkg_dir = self.root / pkg_dir
            tresults.verify_source_digest(source_path, package["input_sha256"])
            tresults.verify_package(pkg_dir, package["sha256"])
        except (tresults.ResultsIntegrityError, KeyError, TypeError) as error:
            raise WorkflowBlockedError(
                f"execution {execution_id} uploaded package fails integrity: "
                f"{error}") from error

    def _observe_testops(self, state, adapter, execution_id, *, variant=None):
        """Refresh publications.testops.last_observation from source state.

        The publication channel belongs to the current head execution: a
        base execution observation never rewrites it — through verify,
        reconcile or any other caller (21B F6). A corrupt execution state
        is a controlled block, not a crash (21B F5). Returns the live
        execution state read (or ``None``) so callers can report the
        execution's own status instead of the publication channel's.
        """
        if variant is None:
            variant = next(
                (item.get("variant")
                 for item in state.get("executions") or []
                 if item.get("execution_id") == execution_id), None)
        try:
            testops_state = adapter.read_execution_state(execution_id)
        except tstate.StateCorruptError as error:
            raise WorkflowBlockedError(
                f"TestOps state for {execution_id} is corrupt: "
                f"{error}") from error
        if testops_state is None or variant == "base":
            return testops_state
        pubs = state["publications"]["testops"]
        pubs["execution_id"] = execution_id
        pubs["last_observation"] = {
            "upload_status": (testops_state.get("upload") or {}).get("status"),
            "launch_id": (testops_state.get("launch") or {}).get("id"),
            "checked_at": state_mod.utc_now(),
            "state_sha256": adapter.execution_state_sha256(execution_id)}
        return testops_state

    # -- publish-testops -----------------------------------------------------

    def _scan_prepare_expectations(self, execution_id, results_dir, mapping):
        """Compute exact source/mapping digests for prepare checkpoints."""
        try:
            source_sha = tresults.results_digest(results_dir)
            scanned = tresults.load_results(results_dir)
            tresults.validate_attachments(results_dir, scanned)
            expected_index = {
                sid: self._scenario_contract.index[sid] for sid in mapping
                if sid in self._scenario_contract.index
            }
            if set(expected_index) != set(mapping):
                raise WorkflowBlockedError(
                    "bindings reference scenarios absent from scenario "
                    "contract")
            uuid_to_sid = tresults.scan_assignments(results_dir,
                                                    expected_index)
        except (OSError, tresults.ResultsIntegrityError) as error:
            raise WorkflowBlockedError(
                f"allure results for {execution_id} failed integrity check: "
                f"{error}") from error
        if set(uuid_to_sid.values()) != set(mapping):
            raise WorkflowBlockedError(
                f"allure results for {execution_id} do not cover all "
                "bound scenarios")
        uuid_by_sid = {sid: uuid for uuid, sid in uuid_to_sid.items()}
        status_by_sid = {
            uuid_to_sid[data["uuid"]]: data.get("status")
            for _path, data in scanned
        }
        assignments = {
            uuid_by_sid[sid]: (sid, int(tid))
            for sid, tid in mapping.items()
        }
        return {
            "source_sha256": source_sha,
            "uuid_by_sid": uuid_by_sid,
            "status_by_sid": status_by_sid,
            "assignments": assignments,
            "assignments_sha256": tresults.assignments_digest(assignments),
        }

    def _evaluate_prepare_boundaries(self, execution_id, results_dir, mapping,
                                     expected, testops_state):
        """Return (plan_ok, assign_ok, package_ok) verified against disk."""
        if testops_state is None:
            return False, False, False
        if testops_state.get("execution_id") != execution_id:
            return False, False, False
        res = testops_state.get("results")
        if not isinstance(res, dict) or not res.get("path"):
            return False, False, False
        res_path = Path(res["path"])
        if not res_path.is_absolute():
            res_path = self.root / res_path
        if (res_path.resolve() != results_dir.resolve()
                or res.get("sha256") != expected["source_sha256"]
                or testops_state.get("unmapped")):
            return False, False, False
        scenarios = testops_state.get("scenarios")
        if not isinstance(scenarios, dict) or set(scenarios) != set(mapping):
            return False, False, False
        for sid in mapping:
            rec = scenarios.get(sid) or {}
            if (rec.get("uuid") != expected["uuid_by_sid"][sid]
                    or rec.get("status") != expected["status_by_sid"][sid]):
                return False, False, False
        plan_ok = True

        if tstate.unresolved_ids(testops_state):
            return plan_ok, False, False
        for sid, tid in mapping.items():
            rec = scenarios.get(sid) or {}
            if (rec.get("binding") != "bound"
                    or rec.get("testops_id") != int(tid)):
                return plan_ok, False, False
        assign_ok = True

        pkg = testops_state.get("package")
        if not isinstance(pkg, dict):
            return plan_ok, assign_ok, False
        pkg_sha = pkg.get("sha256")
        raw_dir = pkg.get("dir")
        if (pkg.get("mode") != "bind"
                or pkg.get("results") != len(mapping)
                or pkg.get("input_sha256") != expected["source_sha256"]
                or pkg.get("assignments_sha256")
                != expected["assignments_sha256"]
                or not (isinstance(pkg_sha, str)
                        and state_mod.HEX64.fullmatch(pkg_sha))
                or not isinstance(raw_dir, str) or not raw_dir):
            return plan_ok, assign_ok, False
        pkg_dir = Path(raw_dir)
        if not pkg_dir.is_absolute():
            pkg_dir = self.root / pkg_dir
        try:
            tresults.verify_source_digest(results_dir, pkg["input_sha256"])
            tresults.verify_package(pkg_dir, pkg_sha)
            pkg_scanned = tresults.load_results(pkg_dir)
            if len(pkg_scanned) != len(mapping):
                return plan_ok, assign_ok, False
            tresults.validate_attachments(pkg_dir, pkg_scanned)
        except tresults.ResultsIntegrityError:
            return plan_ok, assign_ok, False
        return plan_ok, assign_ok, True

    @staticmethod
    def _prepare_checkpoint_record(execution_id, expected, plan_ok, assign_ok,
                                   package_ok, testops_state, state_sha):
        pkg_sha = (((testops_state or {}).get("package") or {}).get("sha256")
                   if package_ok else None)
        return {
            "execution_id": execution_id,
            "source_sha256": expected["source_sha256"],
            "assignments_sha256": expected["assignments_sha256"],
            "plan": "completed" if plan_ok else "pending",
            "assign": "completed" if assign_ok else "pending",
            "package": "completed" if package_ok else "pending",
            "package_sha256": pkg_sha,
            "testops_state_sha256": state_sha,
            "updated_at": state_mod.utc_now(),
        }

    def prepare_testops(self, execution_id, workflow_id=None):
        """Local plan → assign → package chain with durable verified skips.

        Checkpoints are bound to exact execution, raw Allure source, binding
        assignments and built package digests. Completed boundaries are
        skipped without dispatching ``run-testops.sh``; a lost workflow save
        after a delegated step is recovered by reading and verifying the
        execution state/package instead of rebuilding blindly. Attempted or
        uploaded executions remain immutable.
        """
        workflow_id = self._resolve_workflow_id(workflow_id)
        workflow_dir = self.workflow_dir(workflow_id)
        adapter = adapters.TestOpsAdapter(self.root, self.runner)
        with self._locked(workflow_dir, operation="prepare-testops"):
            state = state_mod.load_state(workflow_dir)
            if state is None:
                raise WorkflowBlockedError("no state; run init first")
            self._require_fresh(state)
            if state["phase"] != "executed":
                raise WorkflowBlockedError(
                    f"prepare-testops requires phase executed; current "
                    f"phase is {state['phase']}")
            entry = next((item for item in state["executions"]
                          if item["execution_id"] == execution_id), None)
            if entry is None:
                raise WorkflowBlockedError(
                    f"execution {execution_id} is not recorded in this "
                    "workflow")
            if (entry.get("variant") != "head"
                    or entry.get("bound_revision")
                    != state["input"]["revision"]):
                raise WorkflowBlockedError(
                    f"execution {execution_id} is not a current-revision "
                    "head execution")
            if not state_mod.artifact_fresh(state, "bindings"):
                raise WorkflowBlockedError(
                    "prepare-testops requires fresh accepted bindings")
            mapping = {
                sid: int(tid)
                for sid, tid in
                ((state["artifacts"].get("bindings") or {})
                 .get("mapping") or {}).items()
            }
            if not mapping:
                raise WorkflowBlockedError("accepted bindings mapping empty")
            manifest = {}
            try:
                manifest, _ = adapters.read_manifest(entry["evidence_dir"])
            except WorkflowValidationError:
                manifest = {}
            results_dir = Path(entry["evidence_dir"]) / (
                ((manifest or {}).get("artifacts") or {}).get("allure_results")
                or "allure-results")
            if not results_dir.is_dir():
                raise WorkflowBlockedError(
                    f"no allure results directory for {execution_id}: "
                    f"{results_dir}")
            try:
                testops_state = adapter.read_execution_state(execution_id)
            except tstate.StateCorruptError as error:
                raise WorkflowBlockedError(
                    f"TestOps state for {execution_id} is corrupt: "
                    f"{error}") from error
            if testops_state is not None:
                upload = testops_state.get("upload") or {}
                if (upload.get("status") not in (None, "pending")
                        or (upload.get("attempts") or 0) > 0
                        or testops_state.get("launch") is not None):
                    raise WorkflowBlockedError(
                        f"execution {execution_id} already has upload status "
                        f"{upload.get('status')!r} (attempts="
                        f"{upload.get('attempts')}); plan/assign/package "
                        "inputs are immutable after an upload attempt")

            expected = self._scan_prepare_expectations(
                execution_id, results_dir, mapping)
            plan_ok, assign_ok, package_ok = (
                self._evaluate_prepare_boundaries(
                    execution_id, results_dir, mapping, expected,
                    testops_state))
            prior_cp = entry.get("testops_prepare") or {}
            checkpoint = self._prepare_checkpoint_record(
                execution_id, expected, plan_ok, assign_ok, package_ok,
                testops_state, adapter.execution_state_sha256(execution_id))

            if package_ok:
                already_saved = (
                    prior_cp.get("package") == "completed"
                    and prior_cp.get("source_sha256")
                    == checkpoint["source_sha256"]
                    and prior_cp.get("assignments_sha256")
                    == checkpoint["assignments_sha256"]
                    and prior_cp.get("package_sha256")
                    == checkpoint["package_sha256"]
                )
                if not already_saved:
                    entry["testops_prepare"] = checkpoint
                    self._observe_testops(state, adapter, execution_id,
                                          variant="head")
                    state_mod.add_journal(
                        state, "orchestrator", "testops-prepare-recovered",
                        f"{execution_id}: verified plan/assign/package "
                        "recovered from execution state without rebuild")
                    state_mod.save_state(workflow_dir, state)
                return {
                    "outcome": "no-op",
                    "recovered": not already_saved,
                    "steps_run": [],
                    "steps_skipped": ["plan", "assign", "package"],
                    "exit": EXIT_OK,
                }

            entry["testops_prepare"] = checkpoint
            state_mod.save_state(workflow_dir, state)

            steps_run = []
            steps_skipped = []
            step_defs = [
                ("plan", lambda ok: ok[0],
                 adapter.plan_args(execution_id, results_dir)),
                ("assign", lambda ok: ok[1],
                 adapter.assign_args(execution_id, mapping)),
                ("package", lambda ok: ok[2],
                 adapter.package_args(execution_id)),
            ]
            for name, predicate, argv in step_defs:
                ok_tuple = self._evaluate_prepare_boundaries(
                    execution_id, results_dir, mapping, expected,
                    testops_state)
                if predicate(ok_tuple):
                    steps_skipped.append(name)
                    continue
                outcome = adapter.run(argv)
                try:
                    testops_state = adapter.read_execution_state(execution_id)
                except tstate.StateCorruptError as error:
                    raise WorkflowBlockedError(
                        f"TestOps state corrupted during {name}: "
                        f"{error}") from error
                ok_after = self._evaluate_prepare_boundaries(
                    execution_id, results_dir, mapping, expected,
                    testops_state)
                entry["testops_prepare"] = self._prepare_checkpoint_record(
                    execution_id, expected, ok_after[0], ok_after[1],
                    ok_after[2], testops_state,
                    adapter.execution_state_sha256(execution_id))
                if outcome.error or outcome.code != 0:
                    state_mod.record_error(
                        state, "prepare_testops", name,
                        f"{name} exited {outcome.code or outcome.error}")
                    state_mod.save_state(workflow_dir, state)
                    return {"outcome": "failed", "step": name,
                            "steps_run": steps_run,
                            "steps_skipped": steps_skipped,
                            "exit": outcome.code or EXIT_UNKNOWN}
                if not predicate(ok_after):
                    state_mod.record_error(
                        state, "prepare_testops", name,
                        f"{name} exited 0 but checkpoint verification failed")
                    state_mod.save_state(workflow_dir, state)
                    return {"outcome": "blocked", "step": name,
                            "steps_run": steps_run,
                            "steps_skipped": steps_skipped,
                            "exit": EXIT_BLOCKED}
                steps_run.append(name)
                state_mod.add_journal(state, "orchestrator",
                                      f"testops-{name}",
                                      f"{execution_id}: {name} verified")
                state_mod.save_state(workflow_dir, state)

            self._observe_testops(state, adapter, execution_id,
                                  variant="head")
            state_mod.clear_status(state)
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "prepared", "steps_run": steps_run,
                    "steps_skipped": steps_skipped, "exit": EXIT_OK}

    def verify_testops(self, execution_id, workflow_id=None, online=False):
        """Resumable server-side confirmation, separate from upload.

        Durable upload status ``sent`` is the resume boundary: verify runs
        without repeating the upload (``decide_upload`` also refuses a
        resend). Status ``uploaded`` is a confirmed terminal and returns
        a no-op; every other status blocks.
        """
        workflow_id = self._resolve_workflow_id(workflow_id)
        workflow_dir = self.workflow_dir(workflow_id)
        adapter = adapters.TestOpsAdapter(self.root, self.runner)
        with self._locked(workflow_dir, operation="verify-testops"):
            state = state_mod.load_state(workflow_dir)
            if state is None:
                raise WorkflowBlockedError("no state; run init first")
            self._require_fresh(state)
            if state["phase"] == "published":
                return {"outcome": "no-op", "detail": "already published"}
            if state["phase"] != "executed":
                raise WorkflowBlockedError(
                    f"verify-testops requires phase executed; current "
                    f"phase is {state['phase']}")
            if not any(entry["execution_id"] == execution_id
                       for entry in state["executions"]):
                raise WorkflowBlockedError(
                    f"execution {execution_id} is not recorded in this "
                    "workflow")
            if not online:
                raise WorkflowPermissionError(
                    "verify-testops performs remote reads; pass --online")
            try:
                testops_state = adapter.read_execution_state(execution_id)
            except tstate.StateCorruptError as error:
                raise WorkflowBlockedError(
                    f"TestOps state for {execution_id} is corrupt: "
                    f"{error}") from error
            if testops_state is None:
                raise WorkflowBlockedError(
                    f"no TestOps state for {execution_id}")
            status = (testops_state.get("upload") or {}).get("status")
            if status == "uploaded":
                self._observe_testops(state, adapter, execution_id)
                state_mod.save_state(workflow_dir, state)
                return {"outcome": "no-op",
                        "detail": "upload already confirmed server-side"}
            if status != "sent":
                raise WorkflowBlockedError(
                    f"upload status is {status!r}; verify resumes only "
                    "from a durable sent/uploaded state")
            return self._dispatch_verify(state, workflow_dir, adapter,
                                         execution_id)

    def _dispatch_verify(self, state, workflow_dir, adapter, execution_id):
        """Run the delegated verify argv behind a durable verify intent."""
        intent = None
        for candidate in state_mod.unfinished_intents(state):
            if (candidate.get("operation") == "testops.verify"
                    and candidate.get("target", {}).get("execution")
                    == execution_id):
                intent = candidate
                break
        if intent is None:
            intent = state_mod.new_intent(
                state, "testops.verify", {"execution": execution_id})
        if intent["status"] != "declared":
            # A verify read is idempotent: an unfinished verify intent may
            # be re-run safely; settle it and declare a fresh attempt.
            state_mod.set_intent(
                intent, "failed",
                {"detail": "verify attempt superseded; remote reads are "
                           "idempotent so re-running is safe"})
            intent = state_mod.new_intent(
                state, "testops.verify", {"execution": execution_id})
        intent["status"] = "dispatched"
        intent["dispatched_at"] = state_mod.utc_now()
        state_mod.save_state(workflow_dir, state)
        try:
            outcome = adapter.run(adapter.verify_args(execution_id))
        except KeyboardInterrupt:
            state_mod.set_intent(intent, "unknown",
                                 {"detail": "interrupted during verify"})
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "interrupted", "exit": EXIT_INTERRUPTED}
        except Exception as error:
            state_mod.set_intent(
                intent, "unknown",
                {"detail": f"runner raised {type(error).__name__}"})
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "unknown", "exit": EXIT_UNKNOWN}
        observed_state = self._observe_testops(state, adapter, execution_id)
        observed = ((observed_state or {}).get("upload") or {}).get("status")
        if outcome.error or outcome.code != 0:
            state_mod.set_intent(
                intent, "completed",
                {"outcome": "unconfirmed",
                 "exit_code": outcome.code,
                 "detail": f"verify exited {outcome.code or outcome.error}; "
                           f"upload status observed {observed}"})
            state_mod.record_error(state, "verify_testops", "exit_nonzero",
                                   f"verify exited {outcome.code}")
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "unconfirmed", "exit": EXIT_UNKNOWN}
        state_mod.set_intent(
            intent, "completed",
            {"outcome": "verified" if observed == "uploaded"
             else "unconfirmed",
             "exit_code": outcome.code})
        state_mod.refresh_phase(state)
        state_mod.save_state(workflow_dir, state)
        if observed == "uploaded":
            return {"outcome": "uploaded", "exit": EXIT_OK}
        return {"outcome": "unconfirmed", "exit": EXIT_UNKNOWN,
                "detail": "verify ran but the execution state did not "
                          "reach uploaded"}

    def publish_testops(self, execution_id, workflow_id=None, execute=False):
        workflow_id = self._resolve_workflow_id(workflow_id)
        workflow_dir = self.workflow_dir(workflow_id)
        adapter = adapters.TestOpsAdapter(self.root, self.runner)
        with self._locked(workflow_dir, operation="publish-testops"):
            state = state_mod.load_state(workflow_dir)
            if state is None:
                raise WorkflowBlockedError("no state; run init first")
            self._require_fresh(state)
            if state["phase"] == "published":
                return {"outcome": "no-op", "detail": "already published"}
            if state["phase"] != "executed":
                raise WorkflowBlockedError(
                    f"publish-testops requires phase executed; current phase "
                    f"is {state['phase']}")
            entry = next((item for item in state["executions"]
                          if item["execution_id"] == execution_id), None)
            if entry is None:
                raise WorkflowBlockedError(
                    f"execution {execution_id} is not recorded in this "
                    "workflow")
            if (entry.get("variant") != "head"
                    or entry.get("bound_revision")
                    != state["input"]["revision"]):
                raise WorkflowBlockedError(
                    f"execution {execution_id} is not a current-revision "
                    "head execution")
            if not execute:
                raise WorkflowPermissionError(
                    "publish-testops performs external writes; pass "
                    "--execute")
            try:
                testops_state = adapter.read_execution_state(execution_id)
            except tstate.StateCorruptError as error:
                raise WorkflowBlockedError(
                    f"TestOps state for {execution_id} is corrupt: "
                    f"{error}") from error
            if testops_state is None:
                raise WorkflowBlockedError(
                    f"no TestOps state for {execution_id}; run "
                    "plan/assign/package through run-testops.sh first")
            allowed, reason, _ = tlifecycle.decide_upload(testops_state)
            if not allowed:
                raise WorkflowBlockedError(
                    f"upload guard refused before any transport: {reason}")
            if (testops_state.get("package") or {}).get("dir") is None:
                raise WorkflowBlockedError(
                    f"execution {execution_id} has no built package; run "
                    "run-testops.sh package first")
            if not state_mod.artifact_fresh(state, "bindings"):
                raise WorkflowBlockedError(
                    "publish-testops requires fresh accepted bindings")
            mapping = {
                sid: int(tid)
                for sid, tid in
                ((state["artifacts"].get("bindings") or {})
                 .get("mapping") or {}).items()
            }
            manifest, _ = adapters.read_manifest(entry["evidence_dir"])
            results_dir = Path(entry["evidence_dir"]) / (
                ((manifest or {}).get("artifacts") or {}).get("allure_results")
                or "allure-results")
            expected = self._scan_prepare_expectations(
                execution_id, results_dir, mapping)
            _, _, package_ok = self._evaluate_prepare_boundaries(
                execution_id, results_dir, mapping, expected, testops_state)
            if not package_ok:
                raise WorkflowBlockedError(
                    f"execution {execution_id} package failed source/"
                    "assignments/package integrity verification; run "
                    "prepare-testops before publish-testops")
            argv = adapter.upload_args(execution_id)
            intent = state_mod.new_intent(
                state, "testops.upload", {"execution": execution_id},
                argv=argv)
            intent["status"] = "dispatched"
            intent["dispatched_at"] = state_mod.utc_now()
            state_mod.save_state(workflow_dir, state)
            try:
                outcome = adapter.run(argv)
            except KeyboardInterrupt:
                state_mod.set_intent(
                    intent, "unknown",
                    {"exit_code": None,
                     "detail": "interrupted during upload"})
                state_mod.save_state(workflow_dir, state)
                return {"outcome": "interrupted", "exit": EXIT_INTERRUPTED}
            except Exception as error:
                state_mod.set_intent(
                    intent, "unknown",
                    {"exit_code": None,
                     "detail": f"runner raised {type(error).__name__}; "
                               "a partial write cannot be ruled out"})
                state_mod.save_state(workflow_dir, state)
                return {"outcome": "unknown", "exit": EXIT_UNKNOWN}
            code = self._finish_upload_intent(state, workflow_dir, adapter,
                                              execution_id, intent, outcome)
            if code != EXIT_OK:
                return {"outcome": "upload", "exit": code}
            return self._dispatch_verify(state, workflow_dir, adapter,
                                         execution_id)

    def _finish_upload_intent(self, state, workflow_dir, adapter,
                              execution_id, intent, outcome):
        try:
            testops_state = self._observe_testops(
                state, adapter, execution_id, variant="head")
        except WorkflowBlockedError as error:
            # The upload already ran; the intent must not stay dispatched,
            # but a corrupt local state keeps the effect undetermined.
            state_mod.set_intent(
                intent, "unknown",
                {"exit_code": outcome.code,
                 "detail": "post-upload execution state unreadable: "
                           f"{error}"})
            state_mod.record_error(state, "publish_testops",
                                   "state_corrupt", str(error))
            state_mod.save_state(workflow_dir, state)
            return EXIT_UNKNOWN
        if outcome.error == "interrupted":
            state_mod.set_intent(intent, "unknown",
                                 {"exit_code": None,
                                  "detail": "interrupted during upload"})
            state_mod.save_state(workflow_dir, state)
            return EXIT_INTERRUPTED
        if outcome.error == "launch_error":
            state_mod.set_intent(intent, "failed",
                                 {"exit_code": None,
                                  "detail": "upload command could not start"})
            state_mod.save_state(workflow_dir, state)
            return EXIT_LAUNCH_ERROR
        if outcome.error == "timeout" or outcome.code not in (0, None):
            status = ((testops_state or {}).get("upload") or {}).get("status")
            state_mod.set_intent(
                intent, "unknown",
                {"exit_code": outcome.code,
                 "detail": f"upload exit {outcome.code or outcome.error}; "
                           f"execution state now {status}"})
            state_mod.record_error(state, "publish_testops", "exit_nonzero",
                                   f"upload exited {outcome.code}")
            state_mod.save_state(workflow_dir, state)
            return EXIT_UNKNOWN
        state_mod.set_intent(intent, "completed",
                             {"exit_code": outcome.code,
                              "outcome": "sent"})
        state_mod.save_state(workflow_dir, state)
        return EXIT_OK

    # -- reconcile ------------------------------------------------------------

    def reconcile(self, workflow_id=None, online=False):
        """Read-only resolution of unfinished intents; never re-sends."""
        workflow_id = self._resolve_workflow_id(workflow_id)
        workflow_dir = self.workflow_dir(workflow_id)
        adapter = adapters.TestOpsAdapter(self.root, self.runner)
        report = []
        with self._locked(workflow_dir, operation="reconcile"):
            state = state_mod.load_state(workflow_dir)
            if state is None:
                raise WorkflowBlockedError("no state; run init first")
            if self._refresh_inherited_intents(state):
                state_mod.save_state(workflow_dir, state)
            for intent in state_mod.unfinished_intents(state):
                try:
                    report.append(
                        self._reconcile_intent(state, workflow_dir,
                                               adapter, intent, online))
                except Exception as error:
                    # A crash on a late intent must not discard the
                    # resolutions already proven for earlier intents:
                    # every decision is persisted as it is made.
                    state_mod.record_error(
                        state, "reconcile", "intent_error",
                        f"{intent['intent_id']}: {type(error).__name__}: "
                        f"{error}")
                    report.append(
                        {"intent": intent["intent_id"], "action": "error",
                         "detail": "reconcile could not settle this "
                                   "intent; it stays unfinished"})
                state_mod.refresh_phase(state)
                state_mod.save_state(workflow_dir, state)
            pubs = state["publications"]["testops"]
            if pubs.get("execution_id"):
                self._observe_testops(state, adapter, pubs["execution_id"])
            state_mod.refresh_phase(state)
            state_mod.save_state(workflow_dir, state)
        return report

    def _reconcile_intent(self, state, workflow_dir, adapter, intent, online):
        operation = intent["operation"]
        if operation == "run.execution":
            return self._reconcile_run(state, intent)
        if operation in ("testops.upload", "testops.verify"):
            return self._reconcile_upload(state, adapter, intent)
        if operation == "pr.create":
            return self._reconcile_pr(state, intent, online)
        return {"intent": intent["intent_id"], "action": "ignored"}

    def _reconcile_run(self, state, intent):
        evidence = (intent.get("evidence") or {}).get("evidence_dir")
        if not evidence or intent["status"] == "declared":
            return {"intent": intent["intent_id"], "action": "kept",
                    "detail": "run intent without attributed evidence; "
                              "no automatic rerun"}
        try:
            manifest, _sha = adapters.read_manifest(evidence)
        except WorkflowValidationError:
            manifest = None
        recounted = (adapters.junit_summary(Path(evidence) / "junit.xml")
                     if manifest else None)
        if manifest and manifest.get("status") == "completed" \
                and recounted == manifest.get("junit_summary"):
            result = self._adopt_run_evidence(
                state, self.workflow_dir(state["workflow_id"]), intent,
                Path(evidence), manifest.get("exit_code"))
            if result.get("outcome") == "recorded":
                return {"intent": intent["intent_id"], "action": "adopted",
                        "detail": "evidence manifest proves a completed run"}
            return {"intent": intent["intent_id"], "action": "kept",
                    "detail": result.get("detail")
                              or "evidence failed identity checks"}
        return {"intent": intent["intent_id"], "action": "kept",
                "detail": "evidence does not prove completion; intent stays "
                          f"{intent['status']}"}

    def _reconcile_upload(self, state, adapter, intent):
        execution_id = intent.get("target", {}).get("execution")
        try:
            testops_state = adapter.read_execution_state(execution_id)
        except tstate.StateCorruptError as error:
            state_mod.record_error(state, "reconcile",
                                   "testops_state_corrupt",
                                   f"{execution_id}: {error}")
            return {"intent": intent["intent_id"], "action": "blocked",
                    "detail": "execution state corrupt; the intent stays "
                              f"{intent['status']}"}
        if testops_state is None:
            return {"intent": intent["intent_id"], "action": "kept",
                    "detail": "execution state missing"}
        self._observe_testops(state, adapter, execution_id)
        status = (testops_state.get("upload") or {}).get("status")
        if status == "uploaded":
            state_mod.set_intent(intent, "completed",
                                 {"outcome": "uploaded"})
            return {"intent": intent["intent_id"], "action": "adopted",
                    "detail": "execution state confirms uploaded"}
        if status == "sent":
            state_mod.set_intent(intent, "completed",
                                 {"outcome": "sent",
                                  "detail": "delivered; confirmation "
                                            "pending verify"})
            return {"intent": intent["intent_id"], "action": "adopted",
                    "detail": "batch delivered, not yet confirmed"}
        if status == "pending":
            state_mod.set_intent(intent, "failed",
                                 {"outcome": "not_sent",
                                  "detail": "execution state proves no "
                                            "external write; retry is safe"})
            return {"intent": intent["intent_id"], "action": "retryable",
                    "detail": "no server write recorded; a guarded retry is "
                              "allowed"}
        return {"intent": intent["intent_id"], "action": "kept",
                "detail": f"execution state {status} is indeterminate; "
                          "verify or resolve manually before any resend"}

    def _reconcile_pr(self, state, intent, online):
        role = intent.get("target", {}).get("repo")
        entry = (state["publications"].get("pr") or {}).get(role) or {}
        transport = self._pr_transport(role)
        if transport is None or not online:
            return {"intent": intent["intent_id"], "action": "kept",
                    "detail": "no PR transport/online; intent stays "
                              f"{intent['status']}"}
        # Reconcile against the spec snapshot frozen inside the intent at
        # dispatch — a later re-prepare, revision or supersede must not
        # erase or replace the immutable record of what was sent.
        spec = (intent.get("target") or {}).get("spec") or entry.get("spec")
        if not isinstance(spec, dict) or not spec.get("repo") \
                or not spec.get("title_key"):
            entry.update(
                status="blocked",
                blocked_reason="reconcile: no usable spec snapshot on the "
                               "intent or entry; manual resolution "
                               "required")
            return {"intent": intent["intent_id"], "action": "blocked",
                    "detail": "missing/invalid spec snapshot; the create "
                              "outcome stays unresolved"}
        try:
            found = transport.search(self._pr_search_key(role, spec))
        except Exception as error:
            entry.update(
                status="blocked",
                blocked_reason=f"reconcile: fresh search raised "
                               f"{type(error).__name__}; the create "
                               "outcome stays unresolved")
            return {"intent": intent["intent_id"], "action": "blocked",
                    "detail": "fresh search failed; the intent stays "
                              f"{intent['status']}, never converted to "
                              "retry-safe"}
        candidates = [ref for ref in found
                      if adapters.pr_ref_matches(ref, spec)]
        exact = [ref for ref in candidates
                 if self._verify_pr(
                     state, transport, role, spec, ref,
                     require_current_revision=(
                         intent.get("bound_revision")
                         == state["input"]["revision"]))]
        if len(exact) == 1:
            ref = exact[0]
            entry.update(status="verified", spec=spec,
                         spec_sha256=(spec or {}).get("spec_sha256"),
                         number=ref.number, url=ref.url,
                         intent_id=intent["intent_id"])
            state_mod.set_intent(intent, "completed",
                                 {"outcome": "adopted", "number": ref.number})
            return {"intent": intent["intent_id"], "action": "adopted",
                    "detail": f"exact match PR #{ref.number}"}
        if len(exact) > 1 or (candidates and not exact):
            # Ambiguous remote state or a key collision with non-matching
            # content: never treat as retry-safe.
            entry.update(
                status="blocked",
                blocked_reason=f"reconcile: {len(exact)} exact matches, "
                               f"{len(candidates)} key candidates of "
                               f"{len(found)} found; manual resolution "
                               "required")
            return {"intent": intent["intent_id"], "action": "blocked",
                    "detail": "remote candidates do not prove the exact "
                              "spec; intent stays "
                              f"{intent['status']}"}
        if len(found) == 0:
            # 20R contract: a dispatched create whose outcome is unknown is
            # NEVER settled by an empty search — "no proof means blocked".
            # The intent stays unfinished (blocking any new create or
            # re-prepare) and the entry stays blocked. Only a transport
            # proof of the exact spec may settle the intent.
            entry.update(status="blocked",
                         blocked_reason="a dispatched create could not be "
                                        "confirmed and a fresh search found "
                                        "no PR; the intent stays unresolved "
                                        "until remote proof exists")
            return {"intent": intent["intent_id"], "action": "blocked",
                    "detail": "no remote PR recorded by a fresh search; "
                              "the create outcome stays unknown"}
        entry.update(status="blocked",
                     blocked_reason=f"reconcile: {len(found)} foreign "
                                    "candidates found; a dispatched create "
                                    "is never retried blindly")
        return {"intent": intent["intent_id"], "action": "blocked",
                "detail": f"{len(found)} foreign candidates; manual "
                          "resolution required"}

    # -- PR spec / create / search -------------------------------------------

    def _pr_transport(self, role):
        return self.pr_transports.get(role) or self.pr_transports.get("*")

    def _pr_repo_key(self, state, role):
        if role == "app":
            return state["input"]["identity"]["app_repo"]
        local = (state["input"].get("locals") or {}).get("tests_repo_path")
        return state_mod.normalize_repo_key(local or str(self.root))

    def _pr_search_key(self, role, spec):
        spec = spec or {}
        return {"repo": spec.get("repo"),
                "head_branch": spec.get("head_branch"),
                "base_branch": spec.get("base_branch"),
                "title_key": spec.get("title_key")}

    def _candidate_pr_head(self, state, role):
        """Default candidate commit SHA from revision_data, or None.

        A patch digest (app_head.kind='patch') and a dirty tests checkout
        (tests_repo.dirty=True) are NOT immutable Git commits and never
        produce a PR head_sha fallback: their specs remain pending drafts.
        """
        if role == "tests":
            tests_repo = (state["input"]["revision_data"].get("tests_repo")
                          or {})
            if tests_repo.get("dirty"):
                return None
            return tests_repo.get("commit")
        head = state["input"]["revision_data"].get("app_head") or {}
        if head.get("kind") == "commit":
            return head.get("git_sha")
        return None

    def _commit_head_problems(self, state, role, candidate_sha, files=(), *,
                              require_current_revision=True):
        """Verify ``candidate_sha`` is a real Git commit with matching tree."""
        if (not isinstance(candidate_sha, str)
                or not state_mod.HEX40_64.fullmatch(candidate_sha)):
            return ["head_sha is missing or not a 40-64 hex Git commit SHA"]
        candidate_sha = candidate_sha.lower()
        problems = []
        identity = state["input"]["identity"]
        revision_data = state["input"]["revision_data"]

        if role == "app":
            if candidate_sha == identity["app_base_sha"].lower():
                problems.append(
                    "head_sha equals app_base_sha; base commit is not a "
                    "change head")
            try:
                git = self._git(state)
            except WorkflowBlockedError as error:
                problems.append(str(error))
                git = None
            if git is not None:
                obj_type = git.object_type(candidate_sha)
                if obj_type != "commit":
                    problems.append(
                        f"app Git object {candidate_sha} is {obj_type!r}, "
                        "expected an existing 'commit' object")
            app_head = revision_data.get("app_head") or {}
            if require_current_revision:
                if app_head.get("kind") != "commit":
                    problems.append(
                        f"app_head.kind is {app_head.get('kind')!r}; "
                        "verified PR publication requires an immutable "
                        "commit head, not a patch digest or proposed state")
                elif candidate_sha != (app_head.get("git_sha") or "").lower():
                    problems.append(
                        f"head_sha {candidate_sha} does not match recorded "
                        f"app_head.git_sha {app_head.get('git_sha')}")
            if problems or git is None:
                return problems
            if require_current_revision:
                context = state["artifacts"].get("context") or {}
                sources = (context.get("payload") or {}).get("sources") or []
                if not sources:
                    problems.append(
                        "no accepted context sources to verify app commit "
                        "tree against")
                for src in sources:
                    rel = src["path"]
                    tree_sha = git.commit_file_sha256(candidate_sha, rel)
                    if tree_sha is None:
                        problems.append(
                            f"{rel}: missing in app commit "
                            f"{candidate_sha[:12]}")
                    elif tree_sha != src["sha256"].lower():
                        problems.append(
                            f"{rel}: app commit tree sha256 != accepted "
                            "context sha256")
                    elif (src.get("git_blob")
                          and git.commit_blob(candidate_sha, rel)
                          != src["git_blob"].lower()):
                        problems.append(
                            f"{rel}: app commit blob != accepted context "
                            "git_blob")
                for rel in files or ():
                    live_sha = git.file_sha256(rel)
                    tree_sha = git.commit_file_sha256(candidate_sha, rel)
                    if tree_sha is None:
                        problems.append(
                            f"{rel}: declared PR file missing in commit "
                            f"{candidate_sha[:12]}")
                    elif live_sha is not None and tree_sha != live_sha:
                        problems.append(
                            f"{rel}: commit tree sha256 != app checkout")
                diff_files = git.changed_files(identity["app_base_sha"],
                                               candidate_sha)
                if diff_files is not None:
                    if not diff_files:
                        problems.append(
                            "app commit has no changed files relative to "
                            "app_base_sha")
                    elif files and sorted(set(files)) != sorted(
                            set(diff_files)):
                        problems.append(
                            f"declared PR files {sorted(set(files))} != "
                            f"commit diff {sorted(set(diff_files))}")
            return problems

        tests_repo = revision_data.get("tests_repo") or {}
        tgit = self._tests_git(state)
        obj_type = tgit.object_type(candidate_sha) if tgit else None
        if obj_type != "commit":
            problems.append(
                f"tests Git object {candidate_sha} is {obj_type!r}, "
                "expected an existing 'commit' object")
        if require_current_revision:
            if tests_repo.get("dirty"):
                problems.append(
                    "tests_repo is dirty; commit changes and record a clean "
                    "revision before verified PR publication")
            elif candidate_sha != (tests_repo.get("commit") or "").lower():
                problems.append(
                    f"head_sha {candidate_sha} does not match recorded "
                    f"tests_repo.commit {tests_repo.get('commit')}")
        if problems or tgit is None:
            return problems
        if require_current_revision:
            scope = set(contracts.required_source_paths(
                self._source_contract, state))
            req_rel = (revision_data.get("requirements") or {}).get("path")
            if req_rel and not Path(req_rel).is_absolute():
                scope.add(req_rel)
            for art in (state.get("artifacts") or {}).values():
                if (art or {}).get("status") == "accepted":
                    doc_rel = ((art.get("document") or {}).get("path"))
                    if doc_rel and not Path(doc_rel).is_absolute():
                        scope.add(doc_rel)
            scope.update(files or ())
            for rel in sorted(scope):
                live_sha = tgit.file_sha256(rel)
                tree_sha = tgit.commit_file_sha256(candidate_sha, rel)
                if tree_sha is None:
                    problems.append(
                        f"{rel}: missing in tests commit "
                        f"{candidate_sha[:12]}")
                elif live_sha is None or tree_sha != live_sha:
                    problems.append(
                        f"{rel}: tests commit tree sha256 != accepted file")
        return problems

    def pr_prepare(self, role, workflow_id=None, *, title, head_branch,
                   base_branch, files=(), body_path=None, head_sha=None):
        if role not in PR_ROLES:
            raise WorkflowValidationError(
                f"pr repo role must be one of {PR_ROLES}")
        workflow_id = self._resolve_workflow_id(workflow_id)
        workflow_dir = self.workflow_dir(workflow_id)
        with self._locked(workflow_dir, operation="pr-prepare"):
            state = state_mod.load_state(workflow_dir)
            if state is None:
                raise WorkflowBlockedError("no state; run init first")
            self._require_fresh(state)
            if state["phase"] == "published":
                return {"outcome": "no-op", "detail": "already published"}
            entry = state["publications"]["pr"][role]
            if entry.get("status") in ("created", "verified", "intent"):
                return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                        "detail": f"pr.{role} is {entry['status']}; the "
                                  "spec cannot be replaced after dispatch"}
            open_intent = self._open_pr_intent(state, role)
            if open_intent is not None:
                if open_intent["status"] != "declared":
                    return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                            "detail": f"intent "
                                      f"{open_intent['intent_id']} is "
                                      f"{open_intent['status']}; an "
                                      "unresolved create blocks every "
                                      "spec change — reconcile until "
                                      "remote proof exists"}
                # A declared-but-never-dispatched intent provably caused no
                # external effect; superseding it with a new spec is safe.
                state_mod.set_intent(
                    open_intent, "failed",
                    {"outcome": "superseded_spec",
                     "detail": "declared intent replaced by a new spec "
                               "before any dispatch"})
            inherited = self._blocking_inherited(state, workflow_dir, role)
            if inherited:
                return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                        "detail": f"a superseded workflow left unresolved "
                                  f"create {inherited[0]['intent_id']} for "
                                  f"pr.{role}; resolve it in the superseded "
                                  "workflow first"}
            sorted_files = sorted(files)
            if head_sha is not None:
                head_sha = state_mod.require_git_sha(head_sha, "head_sha")
                head_problems = self._commit_head_problems(
                    state, role, head_sha, sorted_files)
                if head_problems:
                    return {
                        "outcome": "blocked",
                        "exit": EXIT_BLOCKED,
                        "detail": ("head_sha failed Git commit/tree "
                                   "verification: "
                                   + "; ".join(head_problems)),
                        "problems": head_problems,
                    }
                resolved_head_sha = head_sha
            else:
                candidate_sha = self._candidate_pr_head(state, role)
                if candidate_sha is None:
                    resolved_head_sha = None
                else:
                    head_problems = self._commit_head_problems(
                        state, role, candidate_sha, sorted_files)
                    if head_problems:
                        return {
                            "outcome": "blocked",
                            "exit": EXIT_BLOCKED,
                            "detail": ("recorded head commit failed Git "
                                       "object/tree verification: "
                                       + "; ".join(head_problems)),
                            "problems": head_problems,
                        }
                    resolved_head_sha = candidate_sha.lower()
            title_key = f"[{workflow_id}]"
            full_title = title if title_key in title \
                else f"{title_key} {title}"
            # Reproducible body contract (22): the exact UTF-8 bytes are
            # kept verbatim — no trim, no newline conversion — and a
            # durable payload snapshot is written into the workflow dir.
            # Absent/empty bodies canonicalize to None/None for new
            # specs; a digest without reproducible text is never stored.
            body_text = None
            body_sha = None
            body_source = None
            body_snapshot = None
            if body_path:
                body_file = Path(body_path)
                if not body_file.is_file():
                    raise WorkflowValidationError(
                        f"body file missing: {body_path}")
                body_bytes = body_file.read_bytes()
                try:
                    candidate = body_bytes.decode("utf-8")
                except UnicodeDecodeError as error:
                    raise WorkflowValidationError(
                        f"body file is not valid UTF-8: {body_path}"
                    ) from error
                if candidate:
                    body_text = candidate
                    body_sha = hashlib.sha256(body_bytes).hexdigest()
                    body_source = {"path": str(body_file.resolve()),
                                   "sha256": body_sha}
                    snapshot_rel = (f"payloads/pr-{role}-body-"
                                    f"{body_sha[:16]}.txt")
                    self._write_payload(workflow_dir, snapshot_rel,
                                        body_bytes)
                    body_snapshot = {"path": snapshot_rel,
                                     "sha256": body_sha}
            spec = {"repo": self._pr_repo_key(state, role),
                    "title_key": title_key, "title": full_title,
                    "body_sha256": body_sha,
                    "body_text": body_text,
                    "body_source": body_source,
                    "body_snapshot": body_snapshot,
                    "files": sorted_files,
                    "head_branch": head_branch,
                    "base_branch": base_branch,
                    "head_sha": resolved_head_sha}
            spec["spec_sha256"] = adapters.spec_digest(spec)
            if entry.get("spec_sha256") == spec["spec_sha256"]:
                return {"outcome": "no-op", "detail": "spec unchanged"}
            entry.update(status="pending", spec=spec,
                         spec_sha256=spec["spec_sha256"], intent_id=None,
                         number=None, url=None,
                         prepared_at=state_mod.utc_now())
            state_mod.add_journal(state, "orchestrator", "pr-prepare",
                                  f"{role}: spec {spec['spec_sha256'][:16]}… "
                                  f"({'draft' if resolved_head_sha is None else 'verified-head'})")
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "prepared",
                    "draft": resolved_head_sha is None,
                    "spec_sha256": spec["spec_sha256"]}

    def pr_search(self, role, workflow_id=None, online=False):
        workflow_id = self._resolve_workflow_id(workflow_id)
        workflow_dir = self.workflow_dir(workflow_id)
        with self._locked(workflow_dir, operation="pr-search"):
            state = state_mod.load_state(workflow_dir)
            if state is None:
                raise WorkflowBlockedError("no state; run init first")
            entry = state["publications"]["pr"][role]
            spec = entry.get("spec")
            if spec is None:
                raise WorkflowBlockedError(
                    f"no spec for pr.{role}; run pr prepare first")
            transport = self._pr_transport(role)
            if transport is None:
                raise WorkflowPermissionError(
                    "no PR transport configured for this stage; live "
                    "transport is future authorized work")
            if not online:
                raise WorkflowPermissionError(
                    "pr search performs a read-only remote query; pass "
                    "--online")
            found = transport.search(self._pr_search_key(role, spec))
            return {"outcome": "searched", "found": len(found),
                    "refs": [vars(ref) for ref in found]}

    def pr_create(self, role, workflow_id=None, execute=False, online=False):
        if role not in PR_ROLES:
            raise WorkflowValidationError(
                f"pr repo role must be one of {PR_ROLES}")
        workflow_id = self._resolve_workflow_id(workflow_id)
        workflow_dir = self.workflow_dir(workflow_id)
        with self._locked(workflow_dir, operation="pr-create"):
            state = state_mod.load_state(workflow_dir)
            if state is None:
                raise WorkflowBlockedError("no state; run init first")
            self._require_fresh(state)
            if state["phase"] == "published":
                return {"outcome": "no-op", "detail": "already published"}
            if state["phase"] != "executed":
                raise WorkflowBlockedError(
                    f"pr create requires phase executed; current phase is "
                    f"{state['phase']}")
            entry = state["publications"]["pr"][role]
            if entry.get("status") == "verified":
                return {"outcome": "no-op", "detail": "PR already verified"}
            if entry.get("status") == "blocked":
                return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                        "detail": f"pr.{role} is blocked; the unresolved "
                                  "create must be reconciled until remote "
                                  "proof exists"}
            spec = entry.get("spec")
            if spec is None:
                raise WorkflowBlockedError(
                    f"no spec for pr.{role}; run pr prepare first")
            open_intent = self._open_pr_intent(state, role)
            if open_intent is not None \
                    and open_intent["status"] != "declared":
                return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                        "detail": f"intent {open_intent['intent_id']} is "
                                  f"{open_intent['status']}; a dispatched "
                                  "create is never retried blindly — "
                                  "reconcile with a fresh search first"}
            inherited = self._blocking_inherited(state, workflow_dir, role)
            if inherited:
                return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                        "detail": f"a superseded workflow left unresolved "
                                  f"create {inherited[0]['intent_id']} for "
                                  f"pr.{role}; resolve it in the superseded "
                                  "workflow first"}
            transport = self._pr_transport(role)
            if transport is None:
                raise WorkflowPermissionError(
                    "no PR transport configured for this stage; live "
                    "transport is future authorized work")
            if not (execute and online):
                raise WorkflowPermissionError(
                    "pr create needs --execute and --online")
            head_problems = self._commit_head_problems(
                state, role, spec.get("head_sha"), spec.get("files") or ())
            if not spec.get("head_sha") or head_problems:
                return {
                    "outcome": "blocked",
                    "exit": EXIT_BLOCKED,
                    "detail": (f"pr.{role} spec has no verified immutable "
                               "Git commit head: "
                               + "; ".join(head_problems
                                           or ["draft spec has head_sha=None"])),
                    "problems": head_problems,
                }
            if entry.get("status") == "created":
                return self._reprove_created_pr(
                    state, workflow_dir, transport, role, spec, entry)
            lineage = self._lineage_pr_numbers(state, role)
            if lineage:
                return self._reprove_lineage_pr(
                    state, workflow_dir, transport, role, spec, entry,
                    open_intent, lineage)
            # The dispatch path must carry a reproducible body payload:
            # recorded source/snapshot digests are re-proven before any
            # remote read or POST, and a legacy hash without text is
            # never guessed or rewritten.
            body_problems = self._body_payload_problems(workflow_dir,
                                                      spec)
            if body_problems:
                entry.update(
                    status="blocked",
                    blocked_reason=("PR body payload is not reproducible: "
                                    + "; ".join(body_problems)))
                state_mod.save_state(workflow_dir, state)
                return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                        "detail": entry["blocked_reason"],
                        "problems": body_problems}
            key = self._pr_search_key(role, spec)
            try:
                found = transport.search(key)
            except Exception as error:
                state_mod.record_error(
                    state, "pr_create", "search_error",
                    f"fresh search raised {type(error).__name__}: {error}")
                state_mod.save_state(workflow_dir, state)
                return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                        "detail": "fresh search could not prove remote "
                                  "state; refusing dispatch without "
                                  "proof of absence"}
            matching = [ref for ref in found
                        if adapters.pr_ref_matches(ref, spec)]
            if len(matching) > 1:
                entry.update(status="blocked",
                             blocked_reason="multiple matching PRs found")
                state_mod.save_state(workflow_dir, state)
                return {"outcome": "blocked", "exit": EXIT_BLOCKED}
            if len(matching) == 1:
                ref = matching[0]
                # Adoption requires the exact spec content, not just the
                # search key: a key collision must block, not adopt.
                if not self._verify_pr(state, transport, role, spec, ref):
                    entry.update(status="blocked",
                                 blocked_reason="a PR matches the search "
                                                "key but not the recorded "
                                                "spec content; manual "
                                                "resolution required")
                    state_mod.save_state(workflow_dir, state)
                    return {"outcome": "blocked", "exit": EXIT_BLOCKED}
                entry.update(status="verified", number=ref.number,
                             url=ref.url,
                             intent_id=(open_intent or {}).get("intent_id"))
                if open_intent is not None:
                    state_mod.set_intent(
                        open_intent, "completed",
                        {"outcome": "adopted", "number": ref.number})
                state_mod.refresh_phase(state)
                state_mod.save_state(workflow_dir, state)
                return {"outcome": "adopted", "number": ref.number,
                        "verified": True}
            if len(found) > len(matching):
                entry.update(status="blocked",
                             blocked_reason="foreign PRs match the search "
                                            "key partially; manual "
                                            "resolution required")
                state_mod.save_state(workflow_dir, state)
                return {"outcome": "blocked", "exit": EXIT_BLOCKED}
            intent = open_intent or state_mod.new_intent(
                state, "pr.create",
                {"repo": role, "spec_sha256": spec["spec_sha256"],
                 "spec": dict(spec)})
            intent["status"] = "dispatched"
            intent["dispatched_at"] = state_mod.utc_now()
            entry["status"] = "intent"
            entry["intent_id"] = intent["intent_id"]
            state_mod.save_state(workflow_dir, state)
            return self._dispatch_pr_create(state, workflow_dir, transport,
                                            role, spec, entry, intent)

    def _open_pr_intent(self, state, role):
        for intent in state.get("intents") or []:
            if (intent.get("operation") == "pr.create"
                    and intent.get("target", {}).get("repo") == role
                    and intent.get("status")
                    in state_mod.UNFINISHED_INTENT_STATUSES):
                return intent
        return None

    @staticmethod
    def _inherited_pr_intents(state, role):
        """Unresolved creates inherited from a superseded workflow.

        A new lineage never quietly retries the same logical result: the
        inherited intent stays recorded until it is resolved in the
        superseded workflow.
        """
        return [entry for entry in state.get("inherited_intents") or []
                if entry.get("operation") == "pr.create"
                and entry.get("target", {}).get("repo") == role
                and entry.get("status")
                in state_mod.UNFINISHED_INTENT_STATUSES]

    def _blocking_inherited(self, state, workflow_dir, role):
        """Unresolved inherited creates for ``role``, refreshed first.

        A snapshot inherited at supersede time is re-checked against the
        parent state before it may block: a terminal, provably identical
        parent intent resolves the stale blocker in place (21B F2).
        """
        blockers = self._inherited_pr_intents(state, role)
        if blockers and self._refresh_inherited_intents(state, role):
            state_mod.save_state(workflow_dir, state)
            blockers = self._inherited_pr_intents(state, role)
        return blockers

    def _refresh_inherited_intents(self, state, role=None):
        """Re-verify inherited snapshots against the superseded state.

        The superseded workflow state is only read — never written and
        never locked, so there is no reverse lock ordering or
        cross-lineage deadlock. An inherited intent resolves only when
        the recorded parent lineage carries the SAME intent (id +
        operation + identical target snapshot) in a terminal status.
        Missing/corrupt/ambiguous parents keep the blocker; resolved
        snapshots stay recorded for history, and the parent's remote
        effect is never re-dispatched by the new lineage.
        """
        resolved = False
        for inherited in state.get("inherited_intents") or []:
            if inherited.get("status") \
                    not in state_mod.UNFINISHED_INTENT_STATUSES:
                continue
            target = inherited.get("target") or {}
            if role is not None and target.get("repo") != role:
                continue
            verdict = self._inherited_parent_verdict(state, inherited)
            if verdict is None:
                continue
            inherited["status"] = "resolved"
            inherited["resolved_in_parent"] = verdict
            resolved = True
            state_mod.add_journal(
                state, "orchestrator", "inherited-resolved",
                f"inherited intent {inherited.get('intent_id')} resolved "
                f"in parent {inherited.get('inherited_from')}: "
                f"{verdict['parent_status']}")
        return resolved

    def _ancestor_state(self, state, ancestor_id):
        """Recorded lineage walk to the named ancestor state, or None.

        Ancestors are only read — never written and never locked. The
        walk follows each state's recorded ``supersedes`` link, so an
        ``inherited_from`` id is honoured only when it is reachable
        through the documented ancestry (direct parent or an earlier
        hop re-inherited by a second supersede). Missing/corrupt
        ancestors, id mismatches and cycles all fail closed.
        """
        seen = {state.get("workflow_id")}
        next_id = state.get("supersedes")
        while next_id and next_id not in seen and len(seen) <= 32:
            seen.add(next_id)
            try:
                ancestor = state_mod.load_state(self.workflow_dir(next_id))
            except state_mod.WorkflowStateCorruptError:
                return None
            if ancestor is None \
                    or ancestor.get("workflow_id") != next_id:
                return None
            if next_id == ancestor_id:
                return ancestor
            next_id = ancestor.get("supersedes")
        return None

    def _inherited_parent_verdict(self, state, inherited):
        """Terminal parent proof for an inherited snapshot, or None.

        Returns a small verdict dict only when ``inherited_from`` is
        reachable through the recorded ``supersedes`` ancestry, loads
        cleanly and carries the same intent (id + operation + identical
        target) in a terminal status. Anything else — missing/corrupt
        ancestor, absent intent or an intent that differs under the same
        id — is ambiguous and keeps the blocker.
        """
        parent_id = inherited.get("inherited_from")
        if not parent_id:
            return None
        parent = self._ancestor_state(state, parent_id)
        if parent is None:
            return None
        for candidate in parent.get("intents") or []:
            if candidate.get("intent_id") != inherited.get("intent_id"):
                continue
            if (candidate.get("operation") != inherited.get("operation")
                    or (candidate.get("target") or {})
                    != (inherited.get("target") or {})):
                # Same id, different intent: ambiguous, stays blocked.
                return None
            if candidate.get("status") \
                    in state_mod.UNFINISHED_INTENT_STATUSES:
                return None  # still unresolved upstream: blocker stays
            return {"parent_status": candidate.get("status"),
                    "parent_evidence": candidate.get("evidence"),
                    "checked_at": state_mod.utc_now()}
        return None  # intent absent from the parent: ambiguous

    @staticmethod
    def _lineage_pr_numbers(state, role):
        """Remote PR numbers recorded anywhere in the ancestry.

        A resolved inherited snapshot keeps the parent evidence it was
        settled with, and a snapshot copied from the superseded line may
        carry its own dispatch evidence; a recorded ``number`` is a
        durable known remote effect. A fresh ``search`` can legitimately
        miss a real PR, so before any new create the lineage re-proves
        every known number by targeted get — unfinished snapshots are
        not the only place a remote effect can hide.
        """
        numbers = []
        for inherited in state.get("inherited_intents") or []:
            if inherited.get("operation") != "pr.create" \
                    or (inherited.get("target") or {}).get("repo") != role:
                continue
            evidence = inherited.get("evidence") or {}
            verdict = ((inherited.get("resolved_in_parent") or {})
                       .get("parent_evidence") or {})
            for candidate in (evidence.get("number"),
                              verdict.get("number")):
                if isinstance(candidate, int) \
                        and not isinstance(candidate, bool) \
                        and candidate not in numbers:
                    numbers.append(candidate)
        return numbers

    @staticmethod
    def _body_payload_problems(workflow_dir, spec):
        """Pre-dispatch check that the recorded PR body is reproducible.

        A new-format spec carries ``body_text`` plus the digest of its
        exact UTF-8 bytes, the recorded source-file identity and an
        immutable payload snapshot inside the workflow dir. Every link
        of that chain must still verify before any POST; a missing or
        drifted source/snapshot blocks the dispatch. A legacy spec that
        recorded a body digest without reproducible text is never
        guessed or silently rewritten — the create stays blocked until
        a safe re-prepare produces a new spec.
        """
        spec = spec or {}
        digest = spec.get("body_sha256")
        if "body_text" not in spec:
            if digest:
                return ["legacy spec records body_sha256 without "
                        "body_text; the exact body is not reproducible "
                        "— re-run pr prepare"]
            return []  # legacy spec without a body may proceed
        text = spec.get("body_text")
        if digest is None:
            if text:
                return ["spec body_text is non-empty but body_sha256 is "
                        "null; the spec is inconsistent"]
            return []
        problems = []
        if not isinstance(text, str) or not text:
            problems.append(
                "body_sha256 is recorded but body_text is missing or "
                "empty; the exact body is not reproducible — re-run "
                "pr prepare")
            return problems
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != digest:
            problems.append(
                "spec body_text does not hash to the recorded "
                "body_sha256")
        snapshot = spec.get("body_snapshot")
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        snap_rel = snapshot.get("path")
        snap_sha = snapshot.get("sha256")
        snap_path = None
        if isinstance(snap_rel, str) and snap_rel:
            candidate = (Path(workflow_dir) / snap_rel).resolve()
            try:
                candidate.relative_to(Path(workflow_dir).resolve())
                snap_path = candidate
            except ValueError:
                snap_path = None
        if not isinstance(snap_rel, str) or not snap_rel:
            problems.append("spec has no recorded body payload snapshot")
        elif snap_path is None:
            problems.append("body payload snapshot path escapes the "
                            "workflow dir")
        elif not snap_path.is_file():
            problems.append("durable body payload snapshot is missing")
        elif (not isinstance(snap_sha, str)
                or state_mod.sha256_file(snap_path) != snap_sha
                or snap_sha != digest):
            problems.append("durable body payload snapshot digest does "
                            "not match the recorded body_sha256")
        source = spec.get("body_source")
        source = source if isinstance(source, dict) else {}
        src_path = source.get("path")
        src_sha = source.get("sha256")
        if not isinstance(src_path, str) or not src_path \
                or not isinstance(src_sha, str) or not src_sha:
            problems.append("spec has no recorded body source identity")
        else:
            src = Path(src_path)
            actual = state_mod.sha256_file(src) if src.is_file() else None
            if actual != src_sha or actual != digest:
                problems.append("body source file is missing or changed "
                                "since pr prepare; re-run pr prepare")
        return problems

    def _reprove_lineage_pr(self, state, workflow_dir, transport, role,
                            spec, entry, open_intent, numbers):
        """Re-prove remote effects recorded in ancestry; never re-dispatch.

        Resolution of a parent intent proves the old intent finished — it
        never proves absence of its remote effect. Each recorded number
        is re-checked by targeted ``get``: an exact match against the
        CURRENT spec (commit/tree/exact-spec guards) is adopted; a
        missing, mismatched or unreadable ref keeps the lineage
        blocked/unknown. A proven 404 never authorizes a recreate
        automatically.
        """
        indeterminate = False
        for number in numbers:
            try:
                ref = transport.get(spec.get("repo"), number)
            except Exception as error:
                indeterminate = True
                state_mod.record_error(
                    state, "pr_create", "get_error",
                    f"targeted get of lineage PR #{number} raised "
                    f"{type(error).__name__}: {error}")
                continue
            if ref is not None and self._verify_pr(
                    state, transport, role, spec, ref):
                entry.update(
                    status="verified", number=ref.number,
                    url=getattr(ref, "url", None) or entry.get("url"),
                    intent_id=(open_intent or {}).get("intent_id"))
                if open_intent is not None:
                    state_mod.set_intent(
                        open_intent, "completed",
                        {"outcome": "adopted", "number": ref.number})
                state_mod.refresh_phase(state)
                state_mod.add_journal(
                    state, "orchestrator", "pr-create",
                    f"{role}: lineage PR #{ref.number} adopted by "
                    "targeted get")
                state_mod.save_state(workflow_dir, state)
                return {"outcome": "adopted", "number": ref.number,
                        "verified": True}
        if indeterminate:
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "unknown", "exit": EXIT_UNKNOWN,
                    "detail": "targeted get of a lineage PR failed; the "
                              "remote effect is indeterminate and a new "
                              "create is never dispatched automatically"}
        entry.update(
            status="blocked",
            blocked_reason=(
                f"a PR recorded in the superseded lineage "
                f"({', '.join(f'#{n}' for n in numbers)}) could not be "
                "re-proven as the exact current spec by targeted get; "
                "the remote effect stays recorded and no new create is "
                "dispatched"))
        state_mod.save_state(workflow_dir, state)
        return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                "detail": entry["blocked_reason"]}

    def _reprove_created_pr(self, state, workflow_dir, transport, role,
                            spec, entry):
        """Re-prove a recorded create by targeted get; never re-dispatch.

        A ``created`` entry means the transport returned a readable PR
        reference that post-create verification could not confirm. A
        later fresh search that misses it is never a licence for a
        second create (21B F1): only a targeted ``get`` of the recorded
        number plus the exact spec/commit/tree check may settle the
        publication. None/404, transport errors and mismatched content
        all keep the recorded number and stay blocked/unknown — even a
        proven 404 never authorizes a new create automatically. The same
        rule holds after re-prepare, revision and supersede: a recorded
        remote effect is always re-proven before any new dispatch.
        """
        number = entry.get("number")
        if number is None:
            entry["blocked_reason"] = (
                "entry is 'created' but no remote number is recorded; "
                "manual resolution required")
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                    "detail": entry["blocked_reason"]}
        try:
            ref = transport.get(spec.get("repo"), number)
        except Exception as error:
            state_mod.record_error(
                state, "pr_create", "get_error",
                f"targeted get of recorded PR #{number} raised "
                f"{type(error).__name__}: {error}")
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "unknown", "exit": EXIT_UNKNOWN,
                    "detail": f"targeted get of recorded PR #{number} "
                              "failed; the remote effect is indeterminate "
                              "and a new create is never dispatched "
                              "automatically"}
        if ref is not None and self._verify_pr(
                state, transport, role, spec, ref):
            entry.update(status="verified", number=ref.number,
                         url=getattr(ref, "url", None) or entry.get("url"))
            state_mod.refresh_phase(state)
            state_mod.add_journal(
                state, "orchestrator", "pr-create",
                f"{role}: recorded PR #{ref.number} verified by "
                "targeted get")
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "verified", "number": ref.number,
                    "exit": EXIT_OK}
        entry["blocked_reason"] = (
            f"recorded PR #{number} could not be re-proven by targeted "
            f"get ({'not found' if ref is None else 'verification failed'});"
            " the remote effect stays recorded and no new create is "
            "dispatched")
        state_mod.save_state(workflow_dir, state)
        return {"outcome": "blocked", "exit": EXIT_BLOCKED,
                "detail": entry["blocked_reason"]}

    def _dispatch_pr_create(self, state, workflow_dir, transport, role,
                            spec, entry, intent):
        try:
            result = transport.create(spec)
        except KeyboardInterrupt:
            state_mod.set_intent(intent, "unknown",
                                 {"detail": "interrupted during create"})
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "interrupted", "exit": EXIT_INTERRUPTED}
        except Exception as error:  # transport failure is indeterminate
            entry["status"] = "unknown"
            state_mod.set_intent(intent, "unknown",
                                 {"detail": f"create raised "
                                            f"{type(error).__name__}; the "
                                            "remote write cannot be ruled "
                                            "out"})
            state_mod.record_error(state, "pr_create", "transport_error",
                                   str(error)[:300])
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "unknown", "exit": EXIT_UNKNOWN}
        if isinstance(result, adapters.RunOutcome):
            if result.code != 0 or result.error:
                entry["status"] = "unknown"
                state_mod.set_intent(
                    intent, "unknown",
                    {"exit_code": result.code,
                     "detail": f"create exit {result.code or result.error}"})
                state_mod.record_error(state, "pr_create", "exit_nonzero",
                                       f"create exited {result.code}")
                state_mod.save_state(workflow_dir, state)
                return {"outcome": "unknown", "exit": EXIT_UNKNOWN}
            number = getattr(result, "number", None)
            ref = None
        else:
            ref = result
            number = getattr(result, "number", None)
        if ref is None or number is None:
            entry["status"] = "unknown"
            state_mod.set_intent(intent, "unknown",
                                 {"detail": "create returned an unreadable "
                                            "reference; a PR may exist"})
            state_mod.save_state(workflow_dir, state)
            return {"outcome": "unknown", "exit": EXIT_UNKNOWN}
        # The remote effect is now known: make the readable number/URL
        # durable BEFORE the verification GET. A crash between POST and
        # the first read must never lose the recorded effect or license
        # a second create; a lost save leaves the earlier dispatched
        # intent, which still blocks any retry. A durable number is
        # always re-proven by targeted get, never by a fresh search.
        entry.update(status="created", number=number,
                     url=getattr(ref, "url", None))
        state_mod.set_intent(intent, "completed",
                             {"outcome": "created", "number": number,
                              "url": getattr(ref, "url", None),
                              "verified": None})
        state_mod.save_state(workflow_dir, state)
        verified = self._verify_pr(state, transport, role, spec, ref)
        if verified:
            entry["status"] = "verified"
        evidence = intent.get("evidence") or {}
        evidence["verified"] = verified
        intent["evidence"] = evidence
        state_mod.refresh_phase(state)
        state_mod.add_journal(state, "orchestrator", "pr-create",
                              f"{role}: PR #{number} "
                              f"{'verified' if verified else 'created'}")
        state_mod.save_state(workflow_dir, state)
        return {"outcome": "verified" if verified else "created",
                "number": number, "exit": EXIT_OK}

    def _verify_pr(self, state, transport, role, spec, ref, *,
                   require_current_revision=True):
        """Confirmation needs a verified Git commit head + exact get(number)."""
        spec = spec or {}
        if self._commit_head_problems(
                state, role, spec.get("head_sha"), spec.get("files") or (),
                require_current_revision=require_current_revision):
            return False
        try:
            fetched = transport.get(spec.get("repo"), ref.number)
        except Exception:
            return False
        if fetched is None:
            return False
        return adapters.pr_ref_exact(fetched, spec)

    # -- resume ---------------------------------------------------------------

    def resume(self, workflow_id=None, online=False):
        """Reconcile unfinished intents and report the next actionable step."""
        report = self.reconcile(workflow_id, online=online)
        workflow_id = self._resolve_workflow_id(workflow_id)
        workflow_dir = self.workflow_dir(workflow_id)
        with self._locked(workflow_dir, operation="resume"):
            state = state_mod.load_state(workflow_dir)
            state_mod.refresh_phase(state)
            state_mod.add_journal(state, "orchestrator", "resume",
                                  f"phase={state['phase']} "
                                  f"status={state['phase_status']}")
            state_mod.save_state(workflow_dir, state)
        return {"report": report, "next_step": self._next_step(state)}

    def _next_step(self, state):
        phase = state["phase"]
        unfinished = state_mod.unfinished_intents(state)
        if unfinished:
            return (f"reconcile intents "
                    f"{[i['intent_id'] for i in unfinished]} first")
        if phase == "published":
            return "terminal: nothing to do"
        table = {
            "initialized": "accept context <envelope>",
            "context_ready": "accept scenarios <envelope>",
            "awaiting_review": "accept review <envelope> (or fix scenarios)",
            "approved": "accept implementation <envelope>",
            "implementation_ready": "run-execution / import-execution",
            "executed": "publish-testops --execute / pr create (gated)",
        }
        return table.get(phase, f"resolve phase_status {state['phase_status']}")
