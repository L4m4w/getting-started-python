"""Thin adapters over the existing CLI contracts and read-only git calls.

Every external effect goes through a single injectable ``runner`` so the
whole orchestrator can be exercised offline with fakes that count calls.
The runner executes a fixed allowlist of project entry points with argv
lists (never ``shell=True``); arbitrary commands from inputs are never
executed. Nothing here performs network access by itself — delegated CLIs
keep their own ``--execute``/``--online`` gates.
"""
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

from . import state as state_mod

ALLOWED_TOOLS = (
    "tools/run-tests.sh",
    "tools/compile-tests.sh",
    "tools/run-testops.sh",
    "tools/git.sh",
    "tools/run-java-test.sh",
)
GIT_TIMEOUT_S = 10
SUBPROCESS_TIMEOUT_S = 7200
NODE_ID_RE = re.compile(r"tests/[^\s]+\.py::\S+")


@dataclass
class RunOutcome:
    code: int | None
    stdout: str = ""
    error: str | None = None  # launch_error | timeout | interrupted


class SubprocessRunner:
    """Default runner: streams stdout lines, returns the exit code.

    ``line_callback`` is invoked for every stdout line as it arrives, so a
    caller can persist an evidence link before the child finishes.
    """

    def run(self, argv, cwd, line_callback=None, env=None,
            timeout=SUBPROCESS_TIMEOUT_S):
        argv = validate_argv(argv)
        try:
            process = subprocess.Popen(
                argv, cwd=str(cwd), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True,
                env={**os.environ, **(env or {})})
        except OSError:
            return RunOutcome(None, "", "launch_error")
        lines = []
        try:
            for line in process.stdout:
                lines.append(line)
                if line_callback:
                    line_callback(line.rstrip("\n"))
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            return RunOutcome(None, "".join(lines), "timeout")
        except KeyboardInterrupt:
            try:
                process.terminate()
                process.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
            return RunOutcome(None, "".join(lines), "interrupted")
        return RunOutcome(code, "".join(lines), None)


def validate_argv(argv):
    """Fixed allowlist: ``sh <project tool> ...`` with plain string args."""
    argv = list(argv)
    if len(argv) < 2 or argv[0] != "sh" or argv[1] not in ALLOWED_TOOLS:
        raise state_mod.WorkflowValidationError(
            f"argv is outside the delegated-tools allowlist: {argv!r}")
    if not all(isinstance(arg, str) and arg for arg in argv):
        raise state_mod.WorkflowValidationError("argv must be non-empty strings")
    return argv


def _git_blob_id(content):
    return hashlib.sha1(
        b"blob " + str(len(content)).encode() + b"\x00" + content).hexdigest()


class GitReadAdapter:
    """Bounded read-only git/file identity for one repository checkout."""

    def __init__(self, repo_path):
        self.repo_path = Path(repo_path)

    def _git(self, args):
        try:
            return subprocess.run(
                ["git", "-C", str(self.repo_path), "-c",
                 "core.fsmonitor=false", *args],
                capture_output=True, text=True, check=False,
                timeout=GIT_TIMEOUT_S,
                env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
        except (OSError, subprocess.TimeoutExpired):
            return None

    def file_bytes(self, relpath):
        path = (self.repo_path / relpath).resolve()
        try:
            path.relative_to(self.repo_path.resolve())
        except ValueError:
            return None
        if not path.is_file():
            return None
        return path.read_bytes()

    def file_sha256(self, relpath):
        content = self.file_bytes(relpath)
        return hashlib.sha256(content).hexdigest() if content is not None else None

    def git_blob(self, relpath):
        """blob id via git hash-object, or the same algorithm in-process."""
        result = self._git(["hash-object", "--", relpath])
        if (result is not None and result.returncode == 0
                and re.fullmatch(r"[0-9a-f]{40}", result.stdout.strip())):
            return result.stdout.strip()
        content = self.file_bytes(relpath)
        return _git_blob_id(content) if content is not None else None

    def head_commit(self):
        result = self._git(["rev-parse", "HEAD"])
        if (result is not None and result.returncode == 0
                and re.fullmatch(r"[0-9a-fA-F]{40,64}",
                                 result.stdout.strip())):
            return result.stdout.strip().lower()
        return None

    def is_dirty(self):
        result = self._git(
            ["status", "--porcelain", "--untracked-files=normal"])
        if result is not None and result.returncode == 0:
            return bool(result.stdout.strip())
        return None

    def _git_bytes(self, args):
        try:
            return subprocess.run(
                ["git", "-C", str(self.repo_path), "-c",
                 "core.fsmonitor=false", *args],
                capture_output=True, text=False, check=False,
                timeout=GIT_TIMEOUT_S,
                env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
        except (OSError, subprocess.TimeoutExpired):
            return None

    def object_type(self, rev):
        """Exact Git object type ('commit', 'blob', 'tree', 'tag') or None."""
        if not isinstance(rev, str) or not state_mod.HEX40_64.fullmatch(rev):
            return None
        kind_res = self._git(["cat-file", "-t", rev])
        if kind_res is None or kind_res.returncode != 0:
            return None
        kind = kind_res.stdout.strip()
        if kind == "commit":
            verify = self._git(["rev-parse", "--verify", f"{rev}^{{commit}}"])
            if (verify is None or verify.returncode != 0
                    or verify.stdout.strip().lower() != rev.lower()):
                return None
        return kind or None

    def commit_file_bytes(self, commit_sha, relpath):
        """Raw bytes of ``relpath`` in ``commit_sha``'s tree, or None."""
        if (not isinstance(relpath, str) or not relpath
                or Path(relpath).is_absolute()
                or ".." in Path(relpath).parts):
            return None
        if self.object_type(commit_sha) != "commit":
            return None
        result = self._git_bytes(
            ["cat-file", "blob", f"{commit_sha}:{relpath}"])
        if result is None or result.returncode != 0:
            return None
        return result.stdout

    def commit_file_sha256(self, commit_sha, relpath):
        content = self.commit_file_bytes(commit_sha, relpath)
        return (hashlib.sha256(content).hexdigest()
                if content is not None else None)

    def commit_blob(self, commit_sha, relpath):
        content = self.commit_file_bytes(commit_sha, relpath)
        return _git_blob_id(content) if content is not None else None

    def changed_files(self, base_sha, head_sha):
        """Sorted repo-relative paths changed between two commit objects."""
        if (self.object_type(base_sha) != "commit"
                or self.object_type(head_sha) != "commit"):
            return None
        result = self._git(["diff", "--name-only", base_sha, head_sha, "--"])
        if result is None or result.returncode != 0:
            return None
        return sorted(line.strip() for line in result.stdout.splitlines()
                      if line.strip())


def snapshot_allowlist(root, allowlist):
    """Deterministic digest of an explicit source allowlist.

    Covers tracked and untracked files equally; every entry contributes its
    path and content sha256 (``null`` for missing files) to a canonical
    digest. This is the only supported identity for a dirty tests checkout.
    """
    entries = []
    for relpath in allowlist:
        path = Path(root) / relpath
        entries.append({"path": relpath,
                        "sha256": state_mod.sha256_file(path)
                        if path.is_file() else None})
    return state_mod.canonical_digest(entries)


class HarnessAdapter:
    """Delegation to ``tools/run-tests.sh``/``compile-tests.sh``."""

    def __init__(self, root, runner):
        self.root = Path(root)
        self.runner = runner

    def compile_args(self):
        return ["sh", "tools/compile-tests.sh"]

    def list_args(self):
        return ["sh", "tools/run-tests.sh", "list"]

    def api_run_args(self, *, app_base_sha=None, app_patch_sha256=None,
                     gateway_image_id=None, gateway_container=None,
                     allow_sut=False):
        argv = ["sh", "tools/run-tests.sh", "group", "api"]
        if allow_sut:
            argv.append("--allow-sut")
        for flag, value in (("--app-base-sha", app_base_sha),
                            ("--app-patch-sha256", app_patch_sha256),
                            ("--gateway-image-id", gateway_image_id),
                            ("--gateway-container", gateway_container)):
            if value:
                argv.extend([flag, str(value)])
        return argv

    def run(self, argv, on_line=None):
        return self.runner.run(argv, self.root, line_callback=on_line)

    def run_collecting_evidence(self, argv, on_evidence):
        """Run argv, persisting the evidence dir the moment it is printed."""
        found = []

        def on_line(line):
            prefix = "Run evidence: "
            if line.startswith(prefix):
                candidate = Path(line[len(prefix):].strip())
                found.append(candidate)
                on_evidence(candidate)

        outcome = self.run(argv, on_line=on_line)
        return outcome, (found[0] if found else None)


def manifest_shape_problems(manifest):
    """Container types required before manifest readers dereference fields.

    Missing/null fields keep their old semantics; evidence/provenance gates
    still decide completeness, identity and exact accepted digests.
    """
    if not isinstance(manifest, dict):
        return ["manifest must be an object"]
    problems = []
    for name in ("artifacts", "environment", "selection", "repository",
                 "source_identity"):
        value = manifest.get(name)
        if value is not None and not isinstance(value, dict):
            problems.append(f"manifest.{name} must be an object or null")
    for parent, child, kind in (
            ("environment", "declared", dict),
            ("environment", "container_check", dict),
            ("selection", "targets", list),
            ("source_identity", "copies", list)):
        container = manifest.get(parent)
        if not isinstance(container, dict):
            continue
        value = container.get(child)
        if value is not None and not isinstance(value, kind):
            problems.append(f"manifest.{parent}.{child} has invalid container type")
        elif isinstance(value, list) and any(not isinstance(v, str) for v in value):
            problems.append(f"manifest.{parent}.{child} entries must be strings")
    environment = manifest.get("environment")
    declared = environment.get("declared") if isinstance(environment, dict) else None
    repository = manifest.get("repository")
    for container, field, label in (
            (declared, "app_base_sha", "environment.declared.app_base_sha"),
            (declared, "app_patch_sha256", "environment.declared.app_patch_sha256"),
            (repository, "commit", "repository.commit")):
        if isinstance(container, dict):
            value = container.get(field)
            if value is not None and not isinstance(value, str):
                problems.append(f"manifest.{label} must be a string or null")
    artifacts = manifest.get("artifacts")
    if isinstance(artifacts, dict):
        for key, value in artifacts.items():
            if value is not None and (not isinstance(value, str) or not value):
                problems.append(f"manifest.artifacts.{key} must be a path string or null")
    return problems


def read_manifest(evidence_dir):
    """(manifest, sha256) of a harness evidence dir; corrupt is explicit."""
    path = Path(evidence_dir) / "manifest.json"
    if not path.is_file():
        return None, None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise state_mod.WorkflowValidationError(
            f"evidence manifest unreadable: {path}: {error}") from error
    try:
        data = json.loads(text)
    except ValueError as error:
        raise state_mod.WorkflowValidationError(
            f"evidence manifest is not valid JSON: {path}") from error
    if not isinstance(data, dict) or data.get("schema_version") != 2:
        raise state_mod.WorkflowValidationError(
            f"unsupported evidence manifest schema in {path}")
    shape_problems = manifest_shape_problems(data)
    if shape_problems:
        raise state_mod.WorkflowValidationError(
            "evidence manifest shape rejected: " + "; ".join(shape_problems))
    try:
        digest = state_mod.sha256_file(path)
    except OSError as error:
        raise state_mod.WorkflowValidationError(
            f"evidence manifest unhashable: {path}: {error}") from error
    return data, digest


def junit_summary(path):
    """Recount a junit.xml independently of the manifest copy."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    if root.tag.rsplit("}", 1)[-1] not in ("testsuite", "testsuites"):
        return None
    summary = {"total": 0, "passed": 0, "failed": 0, "errors": 0,
               "skipped": 0}
    for case in root.iter():
        if case.tag.rsplit("}", 1)[-1] != "testcase":
            continue
        tags = {child.tag.rsplit("}", 1)[-1] for child in case}
        outcome = ("errors" if "error" in tags else "failed"
                   if "failure" in tags else "skipped"
                   if "skipped" in tags else "passed")
        summary["total"] += 1
        summary[outcome] += 1
    return summary


def collected_node_ids(stdout):
    return [line for line in (stdout or "").splitlines()
            if NODE_ID_RE.fullmatch(line.strip())]


class TestOpsAdapter:
    """Delegation to ``tools/run-testops.sh`` plus read-only state reads.

    Execution ``state.json`` stays the single source of truth for the
    upload lifecycle: the adapter reads it through the existing loader and
    never writes it — external operations run only as subprocesses of the
    TestOps CLI, which applies its own locks and guards.
    """

    def __init__(self, root, runner):
        self.root = Path(root)
        self.runner = runner

    def state_dir(self, execution_id):
        return self.root / "artifacts" / "testops" / execution_id

    def read_execution_state(self, execution_id, state_dir=None):
        """Read execution state; ``state_dir`` overrides the local
        default with a recorded location (read-only either way)."""
        from infrastructure.reporting.testops import state as tstate
        base = (Path(state_dir) if state_dir is not None
                else self.state_dir(execution_id))
        return tstate.load_state(base)

    def execution_state_sha256(self, execution_id, state_dir=None):
        base = (Path(state_dir) if state_dir is not None
                else self.state_dir(execution_id))
        path = base / "state.json"
        return state_mod.sha256_file(path) if path.is_file() else None

    def plan_args(self, execution_id, results_dir):
        return ["sh", "tools/run-testops.sh", "plan",
                "--execution", execution_id, "--results", str(results_dir)]

    def assign_args(self, execution_id, mapping):
        return ["sh", "tools/run-testops.sh", "assign",
                "--execution", execution_id,
                *[f"{sid}={tid}" for sid, tid in sorted(mapping.items())]]

    def package_args(self, execution_id, mode="bind"):
        return ["sh", "tools/run-testops.sh", "package",
                "--execution", execution_id, "--mode", mode]

    def upload_args(self, execution_id):
        return ["sh", "tools/run-testops.sh", "upload",
                "--execution", execution_id, "--execute"]

    def verify_args(self, execution_id, transport="rest"):
        return ["sh", "tools/run-testops.sh", "verify",
                "--execution", execution_id, "--online",
                "--transport", transport]

    def run(self, argv):
        return self.runner.run(argv, self.root)


@dataclass
class PrRef:
    """A pull request as observed by a transport."""
    repo: str
    number: int
    url: str = None
    title: str = None
    head_branch: str = None
    base_branch: str = None
    head_sha: str = None
    body_sha256: str = None
    files: list = field(default_factory=list)


@dataclass
class PrSpec:
    """The exact intended PR; its canonical digest keys the search.

    ``body_text`` is the reproducible UTF-8 payload the transport must
    POST; ``body_sha256`` is the digest of its exact bytes. For new
    specs absent/empty bodies canonicalize to ``None``/``None`` — a
    recorded digest without reproducible text is never guessed.
    """
    repo: str
    title_key: str
    title: str
    body_sha256: str = None
    body_text: str = None
    files: list = field(default_factory=list)
    head_branch: str = None
    base_branch: str = None
    head_sha: str = None
    spec_sha256: str = None


class PrTransport:
    """Read/create protocol for future PR publication (no live impl in 20).

    ``search(key)`` must perform a fresh server-side query at call time —
    a cached "no PR" answer never proves create is safe. ``create(spec)``
    performs the entity write; ``get(repo, number)`` re-reads one PR for
    post-create verification. Implementations count as transports only
    when explicitly injected; the CLI ships none.
    """

    def search(self, key):  # pragma: no cover - protocol
        raise NotImplementedError

    def create(self, spec):  # pragma: no cover - protocol
        raise NotImplementedError

    def get(self, repo, number):  # pragma: no cover - protocol
        raise NotImplementedError


class FakePrTransport(PrTransport):
    """Deterministic offline transport with call counters.

    ``search_result`` may be a list of :class:`PrRef`, a ``BaseException``
    instance (raised on call) or a callable receiving the key.
    ``create_result`` may be a :class:`PrRef`, ``RunOutcome`` or exception.
    """

    def __init__(self, search_result=None, create_result=None, get_map=None):
        self.search_result = search_result if search_result is not None else []
        self.create_result = create_result
        self.get_map = dict(get_map or {})
        self.calls = []

    def _resolve(self, name, configured, *args):
        self.calls.append((name, args))
        value = configured
        if callable(value):
            value = value(*args)
        if isinstance(value, BaseException):
            raise value
        return value

    def search(self, key):
        return list(self._resolve("search", self.search_result, key) or [])

    def create(self, spec):
        return self._resolve("create", self.create_result, spec)

    def get(self, repo, number):
        value = self.get_map.get((repo, number))
        self.calls.append(("get", (repo, number)))
        if isinstance(value, BaseException):
            raise value
        return value


def spec_digest(spec_dict):
    return state_mod.canonical_digest(spec_dict)


def pr_ref_matches(ref, spec):
    """Candidate match: repo + branches + the deterministic title key."""
    if not isinstance(ref, PrRef) or ref is None:
        return False
    return (ref.repo == spec["repo"]
            and ref.head_branch == spec.get("head_branch")
            and ref.base_branch == spec.get("base_branch")
            and isinstance(ref.title, str)
            and spec["title_key"] in ref.title)


def pr_ref_exact(ref, spec):
    """Verifiable match: the remote data must equal the recorded spec.

    Candidates from ``pr_ref_matches`` are only pointers; a completed
    publication requires the full title, the immutable head SHA recorded
    in the spec, the declared body digest and the declared file list to
    match exactly. A spec without ``head_sha`` can never be verified —
    it stays a local draft.
    """
    if not pr_ref_matches(ref, spec):
        return False
    head_sha = spec.get("head_sha")
    if not head_sha or not isinstance(ref.head_sha, str):
        return False
    if ref.head_sha.lower() != head_sha.lower():
        return False
    if ref.title != spec.get("title"):
        return False
    if ref.body_sha256 != spec.get("body_sha256"):
        return False
    return sorted(ref.files or []) == sorted(spec.get("files") or [])
