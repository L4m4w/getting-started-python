"""Local test commands. No installs, service startup or implicit browser runs."""
import argparse
import compileall
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent.parent
GROUPS = {
    "unit": ["tests/unit"],
    "auth": ["tests/auth"],
    "registration": ["tests/registration"],
    "logout": ["tests/logout"],
    "ui": ["tests/auth", "tests/registration", "tests/logout"],
}


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


def _repository_state():
    """Read only version/state; never retain status paths or Git diagnostics."""
    state = {"commit": None, "dirty": None}
    for key, args in (("commit", ["rev-parse", "HEAD"]),
                      ("dirty", ["status", "--porcelain", "--untracked-files=normal"])):
        try:
            result = subprocess.run(
                ["git", "-c", "core.fsmonitor=false", *args], cwd=ROOT,
                capture_output=True, text=True, check=False, timeout=5,
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
    # Parameter IDs may contain data; version is a free-form CLI value. Keep only
    # structural node IDs and conventional version labels, never environment data.
    version = options.bversion
    manifest = {
        "schema_version": 1,
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
        "exit_code": None,
        "artifacts": {"allure_results": "allure-results", "junit": "junit.xml"},
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
        manifest["finished_at"] = _utc_now()
        manifest["junit_summary"] = _junit_summary(junit_path)
        _write_manifest(manifest_path, manifest)
    return manifest["exit_code"]


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
                     help="acknowledge authorized target access and selected registration writes")
    run.add_argument("--browser", choices=("chrome", "firefox", "chromium"))
    run.add_argument("--bversion")
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
        print("BLOCKED: UI scope needs --allow-sut after target access and any "
              "selected registration writes are authorized.", file=sys.stderr)
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
