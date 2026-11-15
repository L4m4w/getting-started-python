"""Local test commands. No installs, service startup or implicit browser runs."""
import argparse
import compileall
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent.parent
GROUPS = {
    "unit": ["tests/unit"],
    "api": ["tests/api"],
    "auth": ["tests/auth"],
    "registration": ["tests/registration"],
    "logout": ["tests/logout"],
    "ui": ["tests/auth", "tests/registration", "tests/logout"],
}
# Согласованный контракт API-пилота CAT-UPD-VAL: тесты, fixtures, транспорт,
# OAuth, константы и закреплённые зависимости, загружаемые при API-прогоне.
# При изменении набора обязательно поднять версию контракта.
API_CONTRACT_VERSION = "api-contract-v1"
API_SOURCE_FILES = (
    "requirements.txt",
    "conftest.py",
    "settings.py",
    "infrastructure/http/__init__.py",
    "infrastructure/http/client.py",
    "infrastructure/http/oauth.py",
    "test_data/fixtures.py",
    "test_data/users.py",
    "test_data/utils/users.py",
    "test_data/consts/users.py",
    "test_data/consts/category_update.py",
    "tests/api/__init__.py",
    "tests/api/conftest.py",
    "tests/api/test_category_update.py",
    "tests/unit/test_http_client.py",
)
# Файлы с секретами никогда не fingerprint'ятся и не копируются в evidence.
NEVER_EVIDENCE_NAMES = (".env",)
GIT_TIMEOUT_S = 10
DOCKER_TIMEOUT_S = 10


def command(args):
    print("+ " + shlex.join([str(arg) for arg in args]), flush=True)
    result = subprocess.run(args, cwd=ROOT, check=False)
    print(f"Exit code: {result.returncode}", flush=True)
    return result.returncode


def versions():
    print(f"Python {sys.version.split()[0]} ({sys.executable})", flush=True)
    valid = sys.version_info[:2] in ((3, 13), (3, 14))
    if not valid:
        print("BLOCKED: expected Python 3.13 (local/Actions) or 3.14 (Jenkins).")
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pin = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s;]+)", line)
        if pin is None:
            print(f"BLOCKED: unsupported dependency declaration: {line}")
            valid = False
            continue
        name, expected = pin.groups()
        try:
            actual = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            actual = "MISSING"
        print(f"{name}: {actual} (required {expected})")
        valid = valid and actual == expected
    print("Browser, driver cache, credentials and SUT readiness: NOT_VERIFIED.", flush=True)
    return 0 if valid else 69


def pytest_command(selection, options):
    args = [sys.executable, "-m", "pytest", *selection]
    if options.browser:
        args.append(f"--browser={options.browser}")
    if options.bversion:
        args.append(f"--bversion={options.bversion}")
    return args


def selection_for(options, parser):
    if options.scope == "group":
        if options.target not in GROUPS:
            parser.error("group must be one of: " + ", ".join(GROUPS))
        return GROUPS[options.target], options.target != "unit"
    if options.scope == "one":
        selector = options.target or ""
        filename, separator, member = selector.partition("::")
        path = Path(filename)
        resolved = (ROOT / path).resolve()
        tests_root = (ROOT / "tests").resolve()
        if (
            not separator or not member or path.is_absolute()
            or ".." in path.parts or not filename.startswith("tests/")
            or not resolved.is_relative_to(tests_root)
            or not resolved.is_file() or not path.name.startswith("test_")
            or path.suffix != ".py"
        ):
            parser.error("one requires an existing tests/.../test_*.py::Class::method node ID")
        return [selector], not resolved.is_relative_to(tests_root / "unit")
    if options.target:
        parser.error("target is only supported for one/group")
    return ["tests"], options.scope == "all"


def _git(args):
    """One bounded Git read; never shell interpolation or env dumps."""
    try:
        return subprocess.run(
            ["git", "-c", "core.fsmonitor=false", *args], cwd=ROOT,
            capture_output=True, text=True, check=False, timeout=GIT_TIMEOUT_S,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _repository_state():
    """Read only version/state; never retain status paths or Git diagnostics."""
    state = {"commit": None, "dirty": None}
    commit = _git(["rev-parse", "HEAD"])
    if (commit is not None and commit.returncode == 0
            and re.fullmatch(r"[0-9a-fA-F]{40,64}", commit.stdout.strip())):
        state["commit"] = commit.stdout.strip()
    dirty = _git(["status", "--porcelain", "--untracked-files=normal"])
    if dirty is not None and dirty.returncode == 0:
        state["dirty"] = bool(dirty.stdout.strip())
    return state


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_fingerprint(relpath):
    """Bounded identity of one contract source file; missing files stay explicit."""
    entry = {"path": relpath, "sha256": None, "git_blob": None, "tracked": None}
    path = ROOT / relpath
    if not path.is_file():
        return entry
    entry["sha256"] = _sha256(path)
    blob = _git(["hash-object", "--", relpath])
    if (blob is not None and blob.returncode == 0
            and re.fullmatch(r"[0-9a-f]{40}", blob.stdout.strip())):
        entry["git_blob"] = blob.stdout.strip()
    tracked = _git(["ls-files", "--error-unmatch", "--", relpath])
    if tracked is not None:
        entry["tracked"] = tracked.returncode == 0
    return entry


def _api_source_identity(evidence):
    """Fingerprint and copy the agreed API contract sources before pytest runs."""
    files, copies, missing = [], [], []
    for relpath in API_SOURCE_FILES:
        if Path(relpath).name in NEVER_EVIDENCE_NAMES:
            continue
        entry = _source_fingerprint(relpath)
        files.append(entry)
        if entry["sha256"] is None:
            missing.append(relpath)
            continue
        destination = evidence / "sources" / relpath
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relpath, destination)
        copies.append(relpath)
    return {"contract_version": API_CONTRACT_VERSION, "captured_at": _utc_now(),
            "files": files, "copies": copies, "missing": missing,
            "changed_during_run": None, "rechecked_at": None}


def _changed_sources(files):
    """Contract files whose content changed (or appeared/disappeared) mid-run."""
    changed = []
    for entry in files:
        path = ROOT / entry["path"]
        current = _sha256(path) if path.is_file() else None
        if current != entry["sha256"]:
            changed.append(entry["path"])
    return changed


def _is_api_scope(selection):
    """True when the selection executes tests/api (group, node ID or all)."""
    for item in selection:
        node = item.split("[", 1)[0].split("::", 1)[0]
        if node == "tests" or node == "tests/api" or node.startswith("tests/api/"):
            return True
    return False


def _container_check(container, image_id):
    """Distilled docker inspect result; never env, mounts or the raw payload."""
    check = {"performed": False, "reason": None, "checked_at": _utc_now(),
             "container_id": container, "container_name": None,
             "container_running": None, "image_id": None, "image_tag": None,
             "matches_declared_image": None}
    try:
        result = subprocess.run(
            ["docker", "container", "inspect", container],
            capture_output=True, text=True, check=False, timeout=DOCKER_TIMEOUT_S)
    except (OSError, subprocess.TimeoutExpired):
        check["reason"] = "docker unavailable"
        return check
    if result.returncode != 0:
        stderr = (result.stderr or "").lower()
        if "no such" in stderr:
            check["reason"] = "container not found"
        elif "cannot connect" in stderr or "docker daemon" in stderr:
            check["reason"] = "docker daemon unavailable"
        else:
            check["reason"] = "inspect failed"
        return check
    try:
        items = json.loads(result.stdout)
    except ValueError:
        items = None
    data = items[0] if isinstance(items, list) and items else None
    if not isinstance(data, dict):
        check["reason"] = "inspect output unreadable"
        return check
    check["performed"] = True
    check["container_id"] = data.get("Id") or container
    name = data.get("Name")
    check["container_name"] = name.lstrip("/") if isinstance(name, str) else None
    state = data.get("State") if isinstance(data.get("State"), dict) else {}
    check["container_running"] = state.get("Running")
    actual_image = data.get("Image") if isinstance(data.get("Image"), str) else ""
    check["image_id"] = actual_image or None
    config = data.get("Config") if isinstance(data.get("Config"), dict) else {}
    check["image_tag"] = config.get("Image")
    if image_id:
        declared = image_id.removeprefix("sha256:").lower()
        actual = actual_image.removeprefix("sha256:").lower()
        check["matches_declared_image"] = bool(actual) and actual.startswith(declared)
    return check


def _environment_metadata(options):
    """Operator-declared SUT identity plus the actual container check result."""
    declared = {"app_base_sha": options.app_base_sha,
                "app_patch_sha256": options.app_patch_sha256,
                "gateway_image_id": options.gateway_image_id,
                "gateway_container": options.gateway_container}
    if not any(value is not None for value in declared.values()):
        return None
    if options.gateway_container:
        check = _container_check(options.gateway_container, options.gateway_image_id)
    else:
        check = {"performed": False, "reason": "container not declared",
                 "checked_at": None}
    return {"declared": {**declared, "source": "operator",
                         "captured_at": _utc_now()},
            "container_check": check}


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


def _write_manifest(path, manifest):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")
    temporary.replace(path)


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def run_with_evidence(selection, options):
    """Execute one actual run and retain its outcome, including launch failures."""
    parent = ROOT / "artifacts" / "harness"
    parent.mkdir(parents=True, exist_ok=True)
    evidence = Path(tempfile.mkdtemp(prefix="run-", dir=parent))
    manifest_path = evidence / "manifest.json"
    junit_path = evidence / "junit.xml"
    # Identity of the agreed API contract sources and the declared SUT
    # environment is captured before launch so evidence matches the code and
    # gateway build that actually ran.
    source_identity = (_api_source_identity(evidence)
                       if _is_api_scope(selection) else None)
    # Parameter IDs may contain data; version is a free-form CLI value. Keep only
    # structural node IDs and conventional version labels, never environment data.
    version = options.bversion
    manifest = {
        "schema_version": 2,
        "run_id": evidence.name,
        "started_at": _utc_now(),
        "finished_at": None,
        "status": "running",
        "python_version": sys.version.split()[0],
        "repository": _repository_state(),
        "selection": {"scope": options.scope,
                      "targets": [item.split("[", 1)[0] for item in selection],
                      "parameter_ids_omitted": any("[" in item for item in selection),
                      "browser": options.browser,
                      "browser_version": version if version is None or
                      re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", version) else "<omitted>"},
        "source_identity": source_identity,
        "environment": _environment_metadata(options),
        "exit_code": None,
        "artifacts": {"allure_results": "allure-results", "junit": "junit.xml",
                      "sources": "sources" if source_identity else None},
        "junit_summary": None,
    }
    _write_manifest(manifest_path, manifest)
    print(f"Run evidence: {evidence}", flush=True)
    try:
        manifest["exit_code"] = command([
            *pytest_command(selection, options), "-v",
            f"--alluredir={evidence / 'allure-results'}", f"--junitxml={junit_path}",
        ])
        manifest["status"] = "completed"
    except KeyboardInterrupt:
        manifest.update(status="interrupted", exit_code=130)
        print("Run interrupted; evidence retained.", file=sys.stderr)
    except OSError:
        manifest.update(status="launch_error", exit_code=127)
        print("Unable to launch pytest; evidence retained.", file=sys.stderr)
    finally:
        if source_identity is not None:
            source_identity["changed_during_run"] = _changed_sources(
                source_identity["files"])
            source_identity["rechecked_at"] = _utc_now()
        manifest["finished_at"] = _utc_now()
        manifest["junit_summary"] = _junit_summary(junit_path)
        _write_manifest(manifest_path, manifest)
    return manifest["exit_code"]


def _git_sha(value):
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", value):
        raise argparse.ArgumentTypeError(
            "expected a 40-64 hex commit SHA")
    return value.lower()


def _sha256_hex(value):
    if not re.fullmatch(r"[0-9a-fA-F]{64}", value):
        raise argparse.ArgumentTypeError("expected a 64-hex SHA-256 digest")
    return value.lower()


def _image_id(value):
    if not re.fullmatch(r"(?i:sha256:)?[0-9a-fA-F]{12,64}", value):
        raise argparse.ArgumentTypeError(
            "expected a Docker image ID: hex 12-64 chars, optional sha256: prefix")
    return value.lower()


def _container_ref(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", value):
        raise argparse.ArgumentTypeError(
            "expected a container ID or name (letters, digits, _.-)")
    return value


def main():
    os.chdir(ROOT)
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("versions")
    actions.add_parser("check")
    run = actions.add_parser("run")
    run.add_argument("scope", choices=("list", "one", "group", "all"))
    run.add_argument("target", nargs="?")
    run.add_argument("--allow-sut", action="store_true",
                     help="acknowledge authorized target access and selected data writes/cleanup")
    run.add_argument("--browser", choices=("chrome", "firefox", "chromium"))
    run.add_argument("--bversion")
    run.add_argument("--app-base-sha", type=_git_sha,
                     help="application base commit SHA for this SUT")
    run.add_argument("--app-patch-sha256", type=_sha256_hex,
                     help="SHA-256 of the applied application patch, when no head SHA exists")
    run.add_argument("--gateway-image-id", type=_image_id,
                     help="expected Docker image ID of the running gateway")
    run.add_argument("--gateway-container", type=_container_ref,
                     help="running gateway container ID or name; verified via docker inspect")
    options = parser.parse_args()
    if options.action == "versions":
        return versions()
    if options.action == "check":
        status = versions()
        if status:
            return status
        print("Compiling project Python sources (no browser execution).", flush=True)
        # Explicit roots exclude .venv, generated reports and downloaded files.
        sources = [*ROOT.glob("*.py"), *(ROOT / name for name in
                    ("pages", "infrastructure", "test_data", "tests", "tools"))]
        compiled = [compileall.compile_dir(path, quiet=1) if path.is_dir()
                    else compileall.compile_file(path, quiet=1) for path in sources]
        if not all(compiled):
            return 1
        status = command([sys.executable, "-m", "pytest", "--collect-only", "-q", "tests"])
        print("Compilation/collection only; no test scenarios executed.", flush=True)
        return status
    selection, needs_sut = selection_for(options, run)
    # Validate scope and authorization before invoking pytest or loading plugins.
    if needs_sut and not options.allow_sut:
        print("BLOCKED: SUT scope needs --allow-sut after target access and "
              "selected data writes/cleanup are authorized.", file=sys.stderr)
        return 77
    status = versions()
    if status:
        return status
    args = pytest_command(selection, options)
    if options.scope == "list":
        return command([*args, "--collect-only", "-q"])
    # Fresh evidence prevents earlier results being reported as this run.
    return run_with_evidence(selection, options)


if __name__ == "__main__":
    sys.exit(main())
