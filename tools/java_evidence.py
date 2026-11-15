"""Run one Gradle test selector in the application repo and retain run evidence.

This entry point never installs dependencies, never edits the application
checkout and never claims a cached/UP-TO-DATE task as an executed test run.
Gradle output is captured to a per-run log; only JUnit XML files that are new
or changed relative to the pre-run snapshot are copied into evidence.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shlex
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_PARENT = ROOT / "artifacts" / "java"
LABELS = ("baseline", "head")
MODULE_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")
SELECTOR_PATTERN = re.compile(r"[A-Za-z0-9_.$*?]{1,255}")
GIT_TIMEOUT_S = 10
JAVA_TIMEOUT_S = 10
PROCESS_STOP_TIMEOUT_S = 5


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def command(args, cwd, env, log_path):
    """Execute the Gradle command, echo output and persist it to the run log."""
    print("+ " + shlex.join([str(arg) for arg in args]), flush=True)
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        process = subprocess.Popen(
            [str(arg) for arg in args], cwd=cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
            start_new_session=True,
        )
        try:
            for line in process.stdout:
                sys.stdout.write(line)
                sys.stdout.flush()
                log.write(line)
            result = process.wait()
        except BaseException:
            # Only this invocation's new process group is signalled. In
            # particular, never stop a shared Gradle daemon or unrelated Java.
            _stop_process_group(process)
            raise
        finally:
            process.stdout.close()
    print(f"Exit code: {result}", flush=True)
    return result


def _stop_process_group(process):
    """Stop our POSIX session and reap its leader before evidence is finalized."""
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=PROCESS_STOP_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
    else:
        # The leader can exit before descendants. Kill any remaining members
        # of the dedicated group rather than leaving a test worker running.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _repository_state(repo):
    """Read only commit/dirty of the application repo; never file lists or env."""
    state = {"commit": None, "dirty": None}
    for key, args in (("commit", ["rev-parse", "HEAD"]),
                      ("dirty", ["status", "--porcelain", "--untracked-files=normal"])):
        try:
            result = subprocess.run(
                ["git", "-c", "core.fsmonitor=false", *args], cwd=repo,
                capture_output=True, text=True, check=False, timeout=GIT_TIMEOUT_S,
                env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            if key == "dirty":
                state[key] = bool(result.stdout.strip())
            elif re.fullmatch(r"[0-9a-fA-F]{40,64}", result.stdout.strip()):
                state[key] = result.stdout.strip()
    return state


def wrapper_version(repo):
    """Parse gradle-wrapper.properties for the pinned Gradle version."""
    try:
        text = (repo / "gradle" / "wrapper" / "gradle-wrapper.properties").read_text(
            encoding="utf-8")
    except OSError:
        return None
    match = re.search(r"gradle-([0-9][0-9.]*)-(?:bin|all)\.zip", text)
    return match.group(1) if match else None


def java_version(jdk):
    """First line of `java -version` for the selected JDK; None when unavailable."""
    binary = Path(jdk) / "bin" / "java"
    try:
        result = subprocess.run([str(binary), "-version"], capture_output=True,
                                text=True, check=False, timeout=JAVA_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (result.stderr or "") + (result.stdout or "")
    lines = output.splitlines()
    return lines[0].strip() if lines else None


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(repo, args):
    try:
        result = subprocess.run(
            ["git", "-c", "core.fsmonitor=false", *args], cwd=repo,
            capture_output=True, text=True, check=False, timeout=GIT_TIMEOUT_S,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result if result.returncode == 0 else None


def fingerprint(repo, relpath):
    """Bounded identity of one source file; missing files stay explicit."""
    entry = {"path": relpath, "sha256": None, "git_blob": None, "tracked": None}
    path = repo / relpath
    if not path.is_file():
        return entry
    entry["sha256"] = _sha256(path)
    blob = _git(repo, ["hash-object", "--", relpath])
    if blob is not None and re.fullmatch(r"[0-9a-f]{40}", blob.stdout.strip()):
        entry["git_blob"] = blob.stdout.strip()
    tracked = _git(repo, ["ls-files", "--error-unmatch", "--", relpath])
    entry["tracked"] = None if tracked is None else True
    return entry


def resolve_test_file(repo, module, selector):
    """Locate the selector's class under <module>/src/test/java; None for patterns."""
    if "*" in selector or "?" in selector:
        return None
    parts = selector.split(".")
    for end in range(len(parts), 0, -1):
        relative = Path(module, "src", "test", "java", *parts[:end]).with_suffix(".java")
        if (repo / relative).is_file():
            return relative.as_posix()
    return None


def bounded_patch(repo, rel_paths):
    """git diff HEAD limited to fingerprinted paths; untracked files use copies."""
    if not rel_paths:
        return ""
    result = _git(repo, ["--no-pager", "diff", "HEAD", "--no-ext-diff",
                         "--no-textconv", "--", *rel_paths])
    return result.stdout if result is not None else ""


def copy_sources(repo, evidence, rel_paths):
    """Copy explicitly listed files into evidence/sources/ preserving layout."""
    copied = []
    for relpath in rel_paths:
        source = repo / relpath
        if not source.is_file():
            continue
        destination = evidence / "sources" / relpath
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(relpath)
    return copied


def results_dir(repo, module):
    return repo / module / "build" / "test-results" / "test"


def snapshot_results(directory):
    """Content hashes of existing TEST-*.xml so stale reports are not re-counted."""
    snapshot = {}
    if directory.is_dir():
        for path in directory.glob("TEST-*.xml"):
            if path.is_file():
                snapshot[path.name] = _sha256(path)
    return snapshot


def fresh_junit_files(directory, snapshot):
    """JUnit XML files that are new or changed since the pre-run snapshot."""
    fresh = []
    if directory.is_dir():
        for path in sorted(directory.glob("TEST-*.xml")):
            if path.is_file() and snapshot.get(path.name) != _sha256(path):
                fresh.append(path)
    return fresh


def _junit_summary(path):
    """Count testcase outcomes without copying test names, output or properties."""
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None
    if root.tag.rsplit("}", 1)[-1] not in ("testsuite", "testsuites"):
        return None
    summary = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    for case in root.iter():
        if case.tag.rsplit("}", 1)[-1] != "testcase":
            continue
        tags = {child.tag.rsplit("}", 1)[-1] for child in case}
        outcome = ("errors" if "error" in tags else "failed" if "failure" in tags
                   else "skipped" if "skipped" in tags else "passed")
        summary["total"] += 1
        summary[outcome] += 1
    return summary


def merge_summaries(paths):
    """Aggregate only a complete set: any unreadable file makes it unavailable."""
    merged = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    readable = False
    for path in paths:
        summary = _junit_summary(path)
        if summary is None:
            return None
        readable = True
        for key in merged:
            merged[key] += summary[key]
    return merged if readable else None


def cached_execution_detected(log_path, task):
    """Best-effort check whether Gradle reported the test task as not executed."""
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    marker = f"Task {task}"
    return any(marker in line and ("UP-TO-DATE" in line or "FROM-CACHE" in line
                                   or "from cache" in line)
               for line in text.splitlines())


def _write_manifest(path, manifest):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def run_with_evidence(options):
    """Execute one actual Gradle run and retain its outcome, including failures."""
    repo = Path(options.repo).resolve()
    EVIDENCE_PARENT.mkdir(parents=True, exist_ok=True)
    evidence = Path(tempfile.mkdtemp(prefix="run-", dir=EVIDENCE_PARENT))
    manifest_path = evidence / "manifest.json"
    log_path = evidence / "gradle.log"
    junit_dir = evidence / "junit"
    task = f":{options.module}:test"
    # Force execution and prohibit restored build-cache reports. A dedicated
    # no-daemon invocation also keeps cancellation away from shared daemons.
    args = ["sh", "gradlew", f":{options.module}:cleanTest", task,
            "--tests", options.tests, "--no-build-cache", "--rerun-tasks", "--no-daemon"]

    # Identity of the test and the caller-declared target sources is captured
    # before launch so evidence matches the code that actually ran.
    fingerprints = []
    test_relpath = resolve_test_file(repo, options.module, options.tests)
    rel_paths = [test_relpath] if test_relpath else []
    for target in options.targets:
        if target not in rel_paths:
            rel_paths.append(target)
    for relpath in rel_paths:
        fingerprints.append(fingerprint(repo, relpath))
    patch_text = bounded_patch(repo, rel_paths)
    if patch_text:
        (evidence / "source.patch").write_text(patch_text, encoding="utf-8")
    copied = copy_sources(repo, evidence, rel_paths)
    snapshot = snapshot_results(results_dir(repo, options.module))

    manifest = {
        "schema_version": 1,
        "kind": "java-gradle-test",
        "run_id": evidence.name,
        "label": options.label,
        "started_at": _utc_now(),
        "finished_at": None,
        "status": "running",
        "harness_python": sys.version.split()[0],
        "java": {"home": options.jdk, "version": java_version(options.jdk)},
        "application": {"path": str(repo), "gradle_wrapper_version": wrapper_version(repo),
                        **_repository_state(repo)},
        "selection": {"module": options.module, "task": task, "tests": options.tests},
        "command": args,
        "environment_overrides": {"JAVA_HOME": options.jdk},
        "source_identity": {"test_file": test_relpath, "files": fingerprints,
                            "copies": copied,
                            "patch": "source.patch" if patch_text else None},
        "exit_code": None,
        "junit": {"directory": "junit", "files": [], "stale_or_missing": True,
                  "summary": None},
        "cached_execution_detected": None,
        "artifacts": {"gradle_log": "gradle.log", "junit": "junit",
                      "sources": "sources", "patch": "source.patch"},
    }
    _write_manifest(manifest_path, manifest)
    print(f"Run evidence: {evidence}", flush=True)
    try:
        manifest["exit_code"] = command(
            args, cwd=repo, log_path=log_path,
            env={**os.environ, "JAVA_HOME": options.jdk})
        manifest["status"] = "completed"
    except KeyboardInterrupt:
        manifest.update(status="interrupted", exit_code=130)
        print("Run interrupted; evidence retained.", file=sys.stderr)
    except OSError:
        manifest.update(status="launch_error", exit_code=127)
        print("Unable to launch Gradle; evidence retained.", file=sys.stderr)
    finally:
        fresh = fresh_junit_files(results_dir(repo, options.module), snapshot)
        copied_names = []
        junit_dir.mkdir(exist_ok=True)
        for path in fresh:
            shutil.copy2(path, junit_dir / path.name)
            copied_names.append(f"junit/{path.name}")
        manifest["junit"]["files"] = copied_names
        manifest["junit"]["stale_or_missing"] = not copied_names
        manifest["junit"]["summary"] = merge_summaries(fresh) if fresh else None
        manifest["cached_execution_detected"] = cached_execution_detected(log_path, task)
        manifest["finished_at"] = _utc_now()
        _write_manifest(manifest_path, manifest)
    return manifest["exit_code"]


def _module(value):
    if not MODULE_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "module must be a top-level Gradle project name (letters, digits, _-)")
    return value


def _selector(value):
    if not SELECTOR_PATTERN.fullmatch(value):
        raise argparse.ArgumentTypeError(
            "tests selector may contain letters, digits, '.', '$', '*', '?' only")
    return value


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True,
                        help="application repository path (absolute or relative "
                             "to the test project root)")
    parser.add_argument("--jdk", required=True,
                        help="JAVA_HOME used for the Gradle run")
    parser.add_argument("--module", required=True, type=_module,
                        help="top-level Gradle module, e.g. niffler-gateway")
    parser.add_argument("--tests", required=True, type=_selector,
                        help="Gradle --tests selector: FQN, FQN.method or a "
                             "'*'/'?' pattern")
    parser.add_argument("--label", required=True, choices=LABELS,
                        help="experiment label recorded in the manifest")
    parser.add_argument("--target", dest="targets", action="append", default=[],
                        metavar="RELPATH",
                        help="application source file to fingerprint; repeatable")
    return parser


def _validate_inputs(options):
    repo = Path(options.repo).resolve()
    problems = []
    if not repo.is_dir():
        problems.append(f"application repo not found: {repo}")
    elif not (repo / "gradlew").is_file():
        problems.append(f"gradlew not found in application repo: {repo}")
    binary = Path(options.jdk) / "bin" / "java"
    if not (binary.is_file() and os.access(binary, os.X_OK)):
        problems.append(f"executable java not found: {binary}")
    targets = []
    for value in options.targets:
        path = Path(value)
        resolved = (repo / path).resolve()
        if (path.is_absolute() or ".." in path.parts
                or not resolved.is_relative_to(repo)):
            problems.append(f"target must be a relative path inside the repo: {value}")
        elif not resolved.is_file():
            problems.append(f"target file not found: {value}")
        else:
            normalized = resolved.relative_to(repo).as_posix()
            if normalized not in targets:
                targets.append(normalized)
    if problems:
        for problem in problems:
            print(f"BLOCKED: {problem}", file=sys.stderr)
        return None
    options.repo = str(repo)
    options.targets = targets
    return options


def main():
    os.chdir(ROOT)
    parser = build_parser()
    options = parser.parse_args()
    if _validate_inputs(options) is None:
        return 69
    # Fresh evidence prevents earlier results being reported as this run.
    return run_with_evidence(options)


if __name__ == "__main__":
    sys.exit(main())
