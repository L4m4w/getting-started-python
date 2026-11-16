"""Minimal QA workflow orchestrator CLI.

Sequential execution of the fixed MVP stage chain with persisted state,
resume and duplicate protection. All external effects keep their existing
permission gates: delegated test runs need --allow-sut, TestOps upload
needs --execute, PR operations need --execute/--online plus an injected
transport selected by the global --pr-transport flag: the default
`none` keeps PR operations blocked, while `github` wires the accepted
GitHub REST transport that reads GITHUB_TOKEN only inside an authorized
HTTP call).
Exit codes: 0 ok; 2 usage; 69 blocked/corrupt/lock; 75 indeterminate
external outcome; 77 permission flag required; 127 launch error;
130 interrupted.
"""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from infrastructure.reporting.testops.lifecycle import LockHeldError
from infrastructure.workflow import orchestrator as orch
from infrastructure.workflow import state as state_mod

EXIT_BLOCKED = orch.EXIT_BLOCKED
EXIT_UNKNOWN = orch.EXIT_UNKNOWN
EXIT_PERMISSION = orch.EXIT_PERMISSION
EXIT_LAUNCH_ERROR = orch.EXIT_LAUNCH_ERROR
EXIT_INTERRUPTED = orch.EXIT_INTERRUPTED


def _git_sha(value):
    try:
        return state_mod.require_git_sha(value, "SHA")
    except state_mod.WorkflowValidationError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def _sha256_hex(value):
    try:
        return state_mod.require_hex64(value, "SHA-256")
    except state_mod.WorkflowValidationError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


_PR_TRANSPORT_ACTIONS = frozenset({"reconcile", "resume"})
_PR_DISPATCHING_PR_ACTIONS = frozenset({"create", "search"})


def _needs_pr_transport(options):
    """Only commands that can reach a PR transport call get wiring.

    status/init/doctor/prepare and every other action keep no transports
    even when --pr-transport github is passed: selecting a transport is
    not an authorization, and no credential or HTTP access may happen on
    paths that never reach a transport call.
    """
    if options.action in _PR_TRANSPORT_ACTIONS:
        return True
    return (options.action == "pr"
            and options.pr_action in _PR_DISPATCHING_PR_ACTIONS)


def _orchestrator(options):
    pr_transports = None
    if options.pr_transport == "github" and _needs_pr_transport(options):
        # Deferred import and construction: the default `none` and every
        # non-dispatching command never touch this module, and the
        # constructor itself performs no credential or network access.
        from infrastructure.workflow.github import GitHubPrTransport
        transport = GitHubPrTransport()
        pr_transports = {"app": transport, "tests": transport}
    return orch.Orchestrator(ROOT, store_dir=options.store_dir,
                             pr_transports=pr_transports)


def _print(value):
    if isinstance(value, (dict, list)):
        print(json.dumps(value, indent=2, ensure_ascii=False, default=str))
    elif value is not None:
        print(value)


def _exit_of(result):
    if isinstance(result, dict) and "exit" in result:
        return result["exit"]
    return 0


def cmd_init(options, parser):
    if options.app_head_sha:
        head_kind, head_sha, head_git = "commit", None, options.app_head_sha
    elif options.app_patch_sha256:
        head_kind, head_sha, head_git = "patch", options.app_patch_sha256, None
    elif options.proposed:
        head_kind, head_sha, head_git = "none", None, None
    else:
        parser.error("init needs one of --app-head-sha, --app-patch-sha256 "
                     "or --proposed")
    expected = None
    if options.expect_head_passed is not None:
        expected = [{"variant": "head", "required": True, "scope": "api",
                     "expect": {"total": options.expect_head_passed,
                                "passed": options.expect_head_passed,
                                "failed": 0, "errors": 0}}]
    strength = None
    if options.expect_base_failed is not None:
        strength = {"variant": "base", "required": True, "scope": "api",
                    "expect": {"total": options.expect_base_failed,
                               "failed": options.expect_base_failed}}
    workflow_id, outcome = _orchestrator(options).init(
        pilot_id=options.pilot_id, app_repo=options.app_repo,
        app_base_sha=options.app_base_sha, app_head_kind=head_kind,
        app_head_sha256=head_sha, app_head_git_sha=head_git,
        tests_commit=options.tests_commit,
        tests_dirty=options.tests_dirty,
        tests_snapshot_sha256=options.tests_snapshot_sha256,
        tests_repo_path=options.tests_repo_path,
        tests_repo=options.tests_repo,
        requirements_path=options.requirements,
        requirements_version=options.requirements_version,
        requirement_ids=(options.requirement_ids.split(",")
                         if options.requirement_ids else None),
        app_repo_path=options.app_repo_path, supersede=options.supersede,
        expected_executions=expected, strength_evidence=strength)
    _print({"workflow_id": workflow_id, "outcome": outcome})
    return 0


def cmd_status(options, parser):
    _print(_orchestrator(options).status(options.workflow_id))
    return 0


def cmd_accept(options, parser):
    result = _orchestrator(options).accept(
        options.kind, options.envelope, workflow_id=options.workflow_id)
    _print({"accept": options.kind, "outcome": result})
    return 0


def cmd_check(options, parser):
    problems = _orchestrator(options).check(options.workflow_id)
    _print({"problems": problems})
    if problems:
        print("BLOCKED: check reported problems", file=sys.stderr)
        return EXIT_BLOCKED
    return 0


def cmd_run_execution(options, parser):
    result = _orchestrator(options).run_execution(
        options.variant, workflow_id=options.workflow_id,
        allow_sut=options.allow_sut, rerun=options.rerun,
        app_base_sha=options.app_base_sha,
        app_patch_sha256=options.app_patch_sha256,
        gateway_image_id=options.gateway_image_id,
        gateway_container=options.gateway_container)
    _print(result)
    return _exit_of(result)


def cmd_import_execution(options, parser):
    provenance = None
    if options.provenance:
        path = Path(options.provenance)
        if not path.is_file():
            parser.error(f"provenance file not found: {options.provenance}")
        try:
            provenance = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            parser.error(f"provenance file is not valid JSON: {error}")
    result = _orchestrator(options).import_execution(
        options.execution, workflow_id=options.workflow_id,
        provenance=provenance, evidence_root=options.evidence_root)
    _print(result)
    return _exit_of(result)


def cmd_prepare_testops(options, parser):
    result = _orchestrator(options).prepare_testops(
        options.execution, workflow_id=options.workflow_id)
    _print(result)
    return _exit_of(result)


def cmd_publish_testops(options, parser):
    result = _orchestrator(options).publish_testops(
        options.execution, workflow_id=options.workflow_id,
        execute=options.execute)
    _print(result)
    return _exit_of(result)


def cmd_verify_testops(options, parser):
    result = _orchestrator(options).verify_testops(
        options.execution, workflow_id=options.workflow_id,
        online=options.online)
    _print(result)
    return _exit_of(result)


def cmd_reconcile(options, parser):
    _print(_orchestrator(options).reconcile(
        options.workflow_id, online=options.online))
    return 0


def cmd_resume(options, parser):
    _print(_orchestrator(options).resume(
        options.workflow_id, online=options.online))
    return 0


def cmd_doctor(options, parser):
    problems = _orchestrator(options).doctor(options.workflow_id)
    _print({"problems": problems})
    if problems:
        print("BLOCKED: doctor reported problems", file=sys.stderr)
        return EXIT_BLOCKED
    return 0


def cmd_pr(options, parser):
    orchestrator = _orchestrator(options)
    if options.pr_action == "prepare":
        if not (options.title and options.head_branch
                and options.base_branch):
            parser.error("pr prepare requires --title, --head-branch and "
                         "--base-branch")
        result = orchestrator.pr_prepare(
            options.repo, workflow_id=options.workflow_id,
            title=options.title, head_branch=options.head_branch,
            base_branch=options.base_branch,
            files=(options.files.split(",") if options.files else ()),
            body_path=options.body, head_sha=options.head_sha)
        _print(result)
        return _exit_of(result)
    if options.pr_action == "create":
        result = orchestrator.pr_create(
            options.repo, workflow_id=options.workflow_id,
            execute=options.execute, online=options.online)
        _print(result)
        return _exit_of(result)
    if options.pr_action == "search":
        result = orchestrator.pr_search(
            options.repo, workflow_id=options.workflow_id,
            online=options.online)
        _print(result)
        return _exit_of(result)
    return 0


def main():
    os.chdir(ROOT)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-dir",
                        help="workflow store dir (default artifacts/workflow)")
    parser.add_argument("--workflow-id",
                        help="target workflow; optional when only one exists")
    parser.add_argument("--pr-transport", choices=("none", "github"),
                        default="none",
                        help="PR transport wiring: none (default, PR "
                             "operations stay blocked) or github (stdlib "
                             "GitHub REST; reads GITHUB_TOKEN only inside "
                             "an authorized HTTP call)")
    actions = parser.add_subparsers(dest="action", required=True)

    init = actions.add_parser("init", help="create or resume a workflow")
    init.add_argument("--pilot-id", required=True)
    init.add_argument("--app-repo", required=True)
    # Head/base values stay unvalidated here: the orchestrator reports
    # malformed input as a domain rejection (exit 69), not a usage error.
    init.add_argument("--app-base-sha", required=True)
    init.add_argument("--app-head-sha")
    init.add_argument("--app-patch-sha256")
    init.add_argument("--proposed", action="store_true",
                      help="no head change exists yet")
    init.add_argument("--tests-commit")
    init.add_argument("--tests-snapshot-sha256", type=_sha256_hex)
    dirty = init.add_mutually_exclusive_group()
    dirty.add_argument("--tests-clean", dest="tests_dirty",
                       action="store_false",
                       help="declared clean tests checkout")
    dirty.add_argument("--tests-dirty", dest="tests_dirty",
                       action="store_true",
                       help="declared dirty checkout; --tests-snapshot-sha256 "
                            "is then required or auto-computed")
    init.set_defaults(tests_dirty=None)
    init.add_argument("--tests-repo-path")
    init.add_argument("--tests-repo", required=True,
                      help="canonical remote key of the tests "
                           "repository (https/ssh/scp spellings "
                           "normalize to github.com/owner/repo)")
    init.add_argument("--requirements", required=True)
    init.add_argument("--requirements-version", default="1")
    init.add_argument("--requirement-ids",
                      help="comma-separated ids; default: R<n> tokens "
                           "parsed from the file")
    init.add_argument("--app-repo-path",
                      help="local app checkout for source re-verification")
    init.add_argument("--supersede", action="store_true",
                      help="start a linked lineage for a changed base")
    init.add_argument("--expect-head-passed", type=int)
    init.add_argument("--expect-base-failed", type=int)

    actions.add_parser("status")
    accept = actions.add_parser("accept")
    accept.add_argument("kind", choices=state_mod.ARTIFACT_KINDS)
    accept.add_argument("envelope")
    actions.add_parser("check")
    run = actions.add_parser("run-execution")
    run.add_argument("--variant", required=True,
                     choices=state_mod.EXECUTION_VARIANTS)
    run.add_argument("--allow-sut", action="store_true",
                     help="forward the authorized-SUT acknowledgement to "
                          "the delegated harness command")
    run.add_argument("--rerun", action="store_true",
                     help="start a new execution even though a satisfying "
                          "one exists")
    run.add_argument("--app-base-sha", type=_git_sha)
    run.add_argument("--app-patch-sha256", type=_sha256_hex)
    run.add_argument("--gateway-image-id")
    run.add_argument("--gateway-container")
    imp = actions.add_parser("import-execution")
    imp.add_argument("execution")
    imp.add_argument("--provenance",
                     help="JSON file with a versioned "
                          "historical_baseline_acceptance record bound to "
                          "accepted review decisions and evidence digests")
    imp.add_argument("--evidence-root",
                     help="absolute external project root holding "
                          "artifacts/harness/<id> and "
                          "artifacts/testops/<id>; accepted only together "
                          "with --provenance for an accepted historical "
                          "baseline and kept read-only")
    prep = actions.add_parser(
        "prepare-testops",
        help="local plan/assign/package chain for a recorded execution")
    prep.add_argument("--execution", required=True)
    pub = actions.add_parser("publish-testops")
    pub.add_argument("--execution", required=True)
    pub.add_argument("--execute", action="store_true")
    ver = actions.add_parser(
        "verify-testops",
        help="resumable server-side confirmation after a sent upload")
    ver.add_argument("--execution", required=True)
    ver.add_argument("--online", action="store_true")
    rec = actions.add_parser("reconcile")
    rec.add_argument("--online", action="store_true")
    res = actions.add_parser("resume")
    res.add_argument("--online", action="store_true")
    actions.add_parser("doctor")
    pr = actions.add_parser("pr")
    pr_actions = pr.add_subparsers(dest="pr_action", required=True)
    for name in ("prepare", "create", "search"):
        sub = pr_actions.add_parser(name)
        sub.add_argument("--repo", required=True, choices=orch.PR_ROLES)
        sub.add_argument("--online", action="store_true")
        sub.add_argument("--execute", action="store_true")
        sub.add_argument("--title")
        sub.add_argument("--body")
        sub.add_argument("--files")
        sub.add_argument("--head-branch")
        sub.add_argument("--base-branch")
        sub.add_argument("--head-sha", type=_git_sha,
                         help="immutable Git commit SHA verified against "
                              "the repository object/tree; derived from a "
                              "clean committed revision when omitted")

    options = parser.parse_args()
    handlers = {"init": cmd_init, "status": cmd_status,
                "accept": cmd_accept, "check": cmd_check,
                "run-execution": cmd_run_execution,
                "import-execution": cmd_import_execution,
                "prepare-testops": cmd_prepare_testops,
                "publish-testops": cmd_publish_testops,
                "verify-testops": cmd_verify_testops,
                "reconcile": cmd_reconcile, "resume": cmd_resume,
                "doctor": cmd_doctor, "pr": cmd_pr}
    try:
        return handlers[options.action](options, parser)
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return EXIT_INTERRUPTED
    except LockHeldError as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return EXIT_BLOCKED
    except state_mod.WorkflowPermissionError as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return EXIT_PERMISSION
    except state_mod.WorkflowLaunchError as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return EXIT_LAUNCH_ERROR
    except state_mod.WorkflowError as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return EXIT_BLOCKED


if __name__ == "__main__":
    sys.exit(main())
