"""20R-регрессии координатора: F1–F5 и локальная TestOps-цепочка.

Всё offline: фиктивные runner/transport, отдельные tmp-хранилища.
Ни один тест не трогает артефакты реального workflow.
"""
import json

import allure
import pytest

from infrastructure.workflow import adapters
from infrastructure.workflow import state as state_mod
from infrastructure.workflow.orchestrator import Orchestrator
from infrastructure.workflow.state import (
    WorkflowBlockedError, WorkflowValidationError)
from test_data.consts import workflow as C
from test_data.utils import workflow as utils


@pytest.fixture
def project(tmp_path):
    return utils.Project(tmp_path / "proj")


def _state(project, workflow_id=None):
    if workflow_id is not None:
        return state_mod.load_state(project.store_dir / workflow_id)
    return project.workflow_state()


def _to_executed(project):
    orchestrator = project.drive_to_executed()
    assert _state(project)["phase"] == "executed"
    return orchestrator


def _to_commit_executed(project):
    orchestrator = project.drive_commit_to_executed()
    assert _state(project)["phase"] == "executed"
    return orchestrator


def _pr_entry(project, role="app", workflow_id=None):
    return _state(project, workflow_id)["publications"]["pr"][role]


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("F1: неопределённый внешний эффект не стирается")
@allure.severity(allure.severity_level.BLOCKER)
class TestF1UnresolvedExternalEffect:
    def _timeout_transport(self, found):
        return adapters.FakePrTransport(
            search_result=lambda key: list(found),
            create_result=adapters.RunOutcome(None, error="timeout"))

    @allure.title("create timeout → поиск 0 → prepare/revision → "
                  "create остаётся 1")
    def test_unknown_create_survives_prepare_and_revision(self, project):
        _to_commit_executed(project)
        transport = self._timeout_transport([])
        orch = project.orchestrator(pr_transports={"app": transport})
        with allure.step("Prepare и create с таймаутом транспорта"):
            orch.pr_prepare("app", title="first spec", head_branch="head",
                            base_branch="main")
            outcome = orch.pr_create("app", execute=True, online=True)
        assert outcome["exit"] == 75
        with allure.step("Пустой reconcile: blocked, intent остаётся"):
            report = orch.reconcile(online=True)
        assert report[0]["action"] == "blocked"
        state = _state(project)
        assert state["intents"][-1]["status"] == "unknown"
        assert _pr_entry(project)["status"] == "blocked"
        spec_before = _pr_entry(project)["spec"]["spec_sha256"]
        with allure.step("Re-prepare заблокирован, spec не заменён"):
            outcome = orch.pr_prepare(
                "app", title="different title", head_branch="other",
                base_branch="main")
            assert outcome["outcome"] == "blocked"
        assert _pr_entry(project)["spec"]["spec_sha256"] == spec_before
        with allure.step("Новая ревизия входа не стирает intent"):
            project.init(orch, app_head_sha256=C.APP_PATCH_SHA256_2)
            state = _state(project)
            assert state["input"]["revision"] == 2
            open_intents = [i for i in state["intents"]
                            if i["operation"] == "pr.create"
                            and i["status"] == "unknown"]
            assert len(open_intents) == 1
        with allure.step("После ревизии prepare/create по-прежнему "
                         "заблокированы"):
            assert orch.pr_prepare(
                "app", title="third", head_branch="x",
                base_branch="main")["outcome"] == "blocked"
            with pytest.raises(WorkflowBlockedError):
                orch.pr_create("app", execute=True, online=True)
            assert orch.reconcile(online=True)[0]["action"] == "blocked"
        creates = [name for name, _ in transport.calls if name == "create"]
        assert len(creates) == 1

    @allure.title("Supersede переносит intent; новая линия не делает "
                  "второй create")
    def test_unknown_create_survives_supersede(self, project):
        _to_commit_executed(project)
        transport = self._timeout_transport([])
        orch = project.orchestrator(pr_transports={"app": transport})
        orch.pr_prepare("app", title="first spec", head_branch="head",
                        base_branch="main")
        outcome = orch.pr_create("app", execute=True, online=True)
        assert outcome["exit"] == 75
        old_id = _state(project)["workflow_id"]
        with allure.step("Supersede на новый base"):
            new_id, outcome = project.init(
                orch, app_base_sha=C.APP_BASE_SHA_2, supersede=True)
        assert outcome == "created" and new_id != old_id
        new_state = state_mod.load_state(project.store_dir / new_id)
        with allure.step("Unfinished intent перешёл в новую линию"):
            inherited = [i for i in new_state["inherited_intents"]
                         if i["operation"] == "pr.create"]
            assert len(inherited) == 1
            assert inherited[0]["status"] == "unknown"
            assert (inherited[0].get("target") or {}).get("spec"), \
                "снимок spec сохранён в immutable intent"
        with allure.step("Prepare/create новой линии заблокированы"):
            assert orch.pr_prepare(
                "app", title="new lineage", head_branch="h",
                base_branch="m", workflow_id=new_id
            )["outcome"] == "blocked"
            with pytest.raises(WorkflowBlockedError):
                orch.pr_create("app", execute=True, online=True,
                               workflow_id=new_id)
        creates = [name for name, _ in transport.calls if name == "create"]
        assert len(creates) == 1

    @allure.title("Reconcile усваивает intent по снимку spec, не по "
                  "новой записи")
    def test_reconcile_uses_intent_spec_snapshot(self, project):
        _to_commit_executed(project)
        created = {}
        orch0 = project.orchestrator()
        orch0.pr_prepare("app", title="sent spec", head_branch="head",
                         base_branch="main")
        sent_spec = _pr_entry(project)["spec"]

        def create(spec):
            created["spec"] = spec
            return adapters.RunOutcome(None, error="timeout")
        ref = adapters.PrRef(
            repo=sent_spec["repo"], number=42,
            url="https://git.invalid/pr/42", title=sent_spec["title"],
            head_branch=sent_spec["head_branch"],
            base_branch=sent_spec["base_branch"],
            head_sha=sent_spec["head_sha"],
            body_sha256=sent_spec["body_sha256"],
            files=list(sent_spec["files"]))
        transport = adapters.FakePrTransport(
            search_result=lambda key: [ref] if created else [],
            create_result=create,
            get_map={(ref.repo, ref.number): ref})
        orch = project.orchestrator(pr_transports={"app": transport})
        outcome = orch.pr_create("app", execute=True, online=True)
        assert outcome["exit"] == 75
        with allure.step("Reconcile находит точный spec — adoption"):
            report = orch.reconcile(online=True)
        assert report[0]["action"] == "adopted"
        state = _state(project)
        assert _pr_entry(project)["status"] == "verified"
        assert _pr_entry(project)["spec"]["spec_sha256"] == \
            sent_spec["spec_sha256"]


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("F2: единый preflight и строгая идентичность evidence")
@allure.severity(allure.severity_level.BLOCKER)
class TestF2PreflightAndIdentity:
    @allure.title("Дрейф теста после accept блокирует gate; doctor видит")
    def test_drift_between_accept_and_gate(self, project):
        orchestrator = project.drive_to_implementation_ready()
        (project.root / C.TEST_FILES[0]).write_text(
            "# changed after accepted implementation\n")
        with allure.step("run_execution отклонён preflight"):
            with pytest.raises(WorkflowBlockedError):
                orchestrator.run_execution("head")
        with allure.step("doctor сообщает о дрейфе"):
            problems = orchestrator.doctor()
        assert any("implementation" in problem for problem in problems)

    @allure.title("Чужой tests commit в manifest отклоняется")
    def test_wrong_tests_commit(self, project):
        orchestrator = project.drive_to_implementation_ready()
        utils.write_manifest(
            project.root, C.EXECUTION_HEAD, C.HEAD_JUNIT, 0,
            declared={"app_base_sha": C.APP_BASE_SHA,
                      "app_patch_sha256": C.APP_PATCH_SHA256},
            tests_commit=C.TESTS_COMMIT_2)
        outcome = orchestrator.import_execution(C.EXECUTION_HEAD)
        assert outcome["outcome"] == "blocked"

    @allure.title("Чужой app base при верном patch отклоняется")
    def test_wrong_app_base(self, project):
        orchestrator = project.drive_to_implementation_ready()
        utils.write_manifest(
            project.root, C.EXECUTION_HEAD, C.HEAD_JUNIT, 0,
            declared={"app_base_sha": C.APP_BASE_SHA_2,
                      "app_patch_sha256": C.APP_PATCH_SHA256})
        outcome = orchestrator.import_execution(C.EXECUTION_HEAD)
        assert outcome["outcome"] == "blocked"

    @allure.title("Отсутствие source_identity отклоняется")
    def test_missing_source_identity(self, project):
        orchestrator = project.drive_to_implementation_ready()
        utils.write_manifest(
            project.root, C.EXECUTION_HEAD, C.HEAD_JUNIT, 0,
            declared={"app_base_sha": C.APP_BASE_SHA,
                      "app_patch_sha256": C.APP_PATCH_SHA256},
            source_files=None)
        outcome = orchestrator.import_execution(C.EXECUTION_HEAD)
        assert outcome["outcome"] == "blocked"

    @allure.title("Изменённая копия источника отклоняется")
    def test_changed_source_copy(self, project):
        orchestrator = project.drive_to_implementation_ready()
        evidence = utils.write_manifest(
            project.root, C.EXECUTION_HEAD, C.HEAD_JUNIT, 0,
            declared={"app_base_sha": C.APP_BASE_SHA,
                      "app_patch_sha256": C.APP_PATCH_SHA256})
        (evidence / "sources" / C.TEST_FILES[0]).write_text(
            "# mutated copy\n")
        outcome = orchestrator.import_execution(C.EXECUTION_HEAD)
        assert outcome["outcome"] == "blocked"

    @allure.title("Отсутствующая копия источника отклоняется")
    def test_missing_source_copy(self, project):
        orchestrator = project.drive_to_implementation_ready()
        evidence = utils.write_manifest(
            project.root, C.EXECUTION_HEAD, C.HEAD_JUNIT, 0,
            declared={"app_base_sha": C.APP_BASE_SHA,
                      "app_patch_sha256": C.APP_PATCH_SHA256})
        (evidence / "sources" / C.TEST_FILES[0]).unlink()
        outcome = orchestrator.import_execution(C.EXECUTION_HEAD)
        assert outcome["outcome"] == "blocked"

    @allure.title("Источник, изменившийся после прогона, отклоняется")
    def test_changed_source_in_checkout(self, project):
        orchestrator = project.drive_to_implementation_ready()
        extra = "tests/api/extra_source.py"
        (project.root / extra).write_text("# extra\n")
        utils.write_manifest(
            project.root, C.EXECUTION_HEAD, C.HEAD_JUNIT, 0,
            declared={"app_base_sha": C.APP_BASE_SHA,
                      "app_patch_sha256": C.APP_PATCH_SHA256},
            source_files=[extra])
        (project.root / extra).write_text("# changed after run\n")
        outcome = orchestrator.import_execution(C.EXECUTION_HEAD)
        assert outcome["outcome"] == "blocked"

    @allure.title("Несовпадающий image binding отклоняется")
    def test_wrong_image(self, project):
        orchestrator = project.drive_to_implementation_ready()
        utils.write_manifest(
            project.root, C.EXECUTION_HEAD, C.HEAD_JUNIT, 0,
            declared={"app_base_sha": C.APP_BASE_SHA,
                      "app_patch_sha256": C.APP_PATCH_SHA256,
                      "gateway_image_id": "sha256:" + "a" * 64,
                      "gateway_container": "gateway.unit"},
            container_check={"performed": True, "container_running": True,
                             "container_name": "gateway.unit",
                             "image_id": "sha256:" + "b" * 64,
                             "matches_declared_image": False})
        outcome = orchestrator.import_execution(C.EXECUTION_HEAD)
        assert outcome["outcome"] == "blocked"

    @allure.title("Чужой сценарий в junit отклоняется")
    def test_wrong_scenario_set(self, project):
        orchestrator = project.drive_to_implementation_ready()
        utils.write_manifest(
            project.root, C.EXECUTION_HEAD, C.HEAD_JUNIT, 0,
            declared={"app_base_sha": C.APP_BASE_SHA,
                      "app_patch_sha256": C.APP_PATCH_SHA256},
            names=[*utils.scenario_names(2), "FOREIGN-999"])
        outcome = orchestrator.import_execution(C.EXECUTION_HEAD)
        assert outcome["outcome"] == "blocked"

    @allure.title("Полная корректная evidence импортируется")
    def test_valid_manifest_imports(self, project):
        orchestrator = project.drive_to_implementation_ready()
        utils.write_manifest(
            project.root, C.EXECUTION_BASE, C.BASE_JUNIT, 1,
            declared={"app_base_sha": C.APP_BASE_SHA})
        outcome = orchestrator.import_execution(C.EXECUTION_BASE)
        assert outcome["outcome"] == "imported"


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("F3: точная проверка PR-контента")
@allure.severity(allure.severity_level.BLOCKER)
class TestF3ExactPrContent:
    def _spec(self, project, role="app"):
        orch = project.orchestrator()
        orch.pr_prepare(role, title="approved title", head_branch="head",
                        base_branch="main")
        return _pr_entry(project, role)["spec"]

    def _ref(self, spec, **overrides):
        data = dict(repo=spec["repo"], number=13,
                    url="https://git.invalid/pr/13",
                    title=spec["title"],
                    head_branch=spec["head_branch"],
                    base_branch=spec["base_branch"],
                    head_sha=spec["head_sha"],
                    body_sha256=spec["body_sha256"],
                    files=list(spec["files"]))
        data.update(overrides)
        return adapters.PrRef(**data)

    def _create_outcome(self, project, spec, ref):
        transport = adapters.FakePrTransport(
            search_result=[ref],
            get_map={(ref.repo, ref.number): ref})
        orch = project.orchestrator(pr_transports={"app": transport})
        outcome = orch.pr_create("app", execute=True, online=True)
        return outcome, _pr_entry(project)["status"]

    @allure.title("Spec несёт только проверенный commit head; patch → draft")
    def test_spec_records_head_sha(self, project):
        with allure.step("Patch head оставляет app spec черновиком без SHA"):
            _to_executed(project)
            draft_spec = self._spec(project, "app")
            assert draft_spec["head_sha"] is None
            clean_tests_spec = self._spec(project, "tests")
            assert clean_tests_spec["head_sha"] == C.TESTS_COMMIT
        with allure.step("Commit head записывает проверенный Git commit SHA"):
            commit_proj = utils.Project(project.root.parent / "commit_proj")
            _to_commit_executed(commit_proj)
            commit_spec = self._spec(commit_proj, "app")
            assert commit_spec["head_sha"] == C.APP_HEAD_COMMIT_SHA

    @allure.title("Полное совпадение контента — verified")
    def test_exact_match_verified(self, project):
        _to_commit_executed(project)
        spec = self._spec(project)
        ref = self._ref(spec)
        outcome, status = self._create_outcome(project, spec, ref)
        assert outcome["outcome"] == "adopted" and outcome["verified"]
        assert status == "verified"

    @allure.title("Чужой head sha не усваивается")
    def test_wrong_head_rejected(self, project):
        _to_commit_executed(project)
        spec = self._spec(project)
        ref = self._ref(spec, head_sha="f" * 40)
        outcome, status = self._create_outcome(project, spec, ref)
        assert outcome["outcome"] == "blocked" and status == "blocked"

    @allure.title("Отсутствующий head sha не усваивается")
    def test_missing_head_rejected(self, project):
        _to_commit_executed(project)
        spec = self._spec(project)
        ref = self._ref(spec, head_sha=None)
        outcome, status = self._create_outcome(project, spec, ref)
        assert outcome["outcome"] == "blocked" and status == "blocked"

    @allure.title("Несовпадающий полный title не усваивается")
    def test_wrong_title_rejected(self, project):
        _to_commit_executed(project)
        spec = self._spec(project)
        ref = self._ref(spec, title=spec["title_key"] + " unrelated title")
        outcome, status = self._create_outcome(project, spec, ref)
        assert outcome["outcome"] == "blocked" and status == "blocked"

    @allure.title("Несовпадающий body digest не усваивается")
    def test_wrong_body_rejected(self, project):
        _to_commit_executed(project)
        spec = self._spec(project)
        ref = self._ref(spec, body_sha256="0" * 64)
        outcome, status = self._create_outcome(project, spec, ref)
        assert outcome["outcome"] == "blocked" and status == "blocked"

    @allure.title("Несовпадающий список файлов не усваивается")
    def test_wrong_files_rejected(self, project):
        _to_commit_executed(project)
        spec = self._spec(project)
        ref = self._ref(spec, files=["other/file.py"])
        outcome, status = self._create_outcome(project, spec, ref)
        assert outcome["outcome"] == "blocked" and status == "blocked"


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("F4: классификация base/patch/commit")
@allure.severity(allure.severity_level.CRITICAL)
class TestF4VariantClassification:
    @allure.title("Patch-head: base+patch → head, base → base")
    def test_patch_head_revision(self, project):
        identity = {"app_base_sha": C.APP_BASE_SHA}
        revision = {"app_head": {"kind": "patch",
                                 "sha256": C.APP_PATCH_SHA256,
                                 "git_sha": None}}
        head_manifest = {"environment": {"declared": {
            "app_base_sha": C.APP_BASE_SHA,
            "app_patch_sha256": C.APP_PATCH_SHA256}}}
        base_manifest = {"environment": {"declared": {
            "app_base_sha": C.APP_BASE_SHA}}}
        variant = project.orchestrator()._manifest_variant
        matches = project.orchestrator()._manifest_matches_revision
        assert variant(head_manifest, identity, revision) == "head"
        assert matches(head_manifest, identity, revision)
        assert variant(base_manifest, identity, revision) == "base"
        assert matches(base_manifest, identity, revision)

    @allure.title("Commit-head: declared base=head sha → head, не base")
    def test_commit_head_revision(self, project):
        identity = {"app_base_sha": C.APP_BASE_SHA}
        revision = {"app_head": {"kind": "commit",
                                 "git_sha": C.APP_BASE_SHA_2,
                                 "sha256": None}}
        head_manifest = {"environment": {"declared": {
            "app_base_sha": C.APP_BASE_SHA_2}}}
        base_manifest = {"environment": {"declared": {
            "app_base_sha": C.APP_BASE_SHA}}}
        variant = project.orchestrator()._manifest_variant
        matches = project.orchestrator()._manifest_matches_revision
        assert variant(head_manifest, identity, revision) == "head"
        assert matches(head_manifest, identity, revision)
        assert variant(base_manifest, identity, revision) == "base"
        assert matches(base_manifest, identity, revision)

    @allure.title("Без контекста голый base_sha не доказывает base")
    def test_bare_base_sha_not_proven(self):
        manifest = {"environment": {"declared": {
            "app_base_sha": C.APP_BASE_SHA_2}}}
        assert Orchestrator._manifest_variant(manifest) == "head"

    @allure.title("Противоречивые run-args отклоняются до dispatch")
    def test_contradictory_run_args(self, project):
        orchestrator = project.drive_to_implementation_ready()
        with pytest.raises(WorkflowBlockedError):
            orchestrator.run_execution(
                "head", app_patch_sha256=C.APP_PATCH_SHA256_2)
        with pytest.raises(WorkflowBlockedError):
            orchestrator.run_execution(
                "base", app_patch_sha256=C.APP_PATCH_SHA256)
        with pytest.raises(WorkflowBlockedError):
            orchestrator.run_execution(
                "head", app_base_sha=C.APP_BASE_SHA_2)
        runs = [argv for argv in
                project.runner.tool_calls("tools/run-tests.sh")
                if "group" in argv]
        assert runs == []


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("F5: повторный accept идентичного артефакта — no-op")
@allure.severity(allure.severity_level.CRITICAL)
class TestF5RepeatAccept:
    @allure.title("Повторный accept всех видов — no-op без проверок")
    def test_repeat_accept_noop(self, project):
        orchestrator = project.drive_to_executed()
        envelopes = {
            "context": project.context_envelope(),
            "scenarios": project.scenarios_envelope(),
            "review": project.review_envelope(),
            "implementation": project.impl_envelope(),
            "bindings": project.bindings_envelope(),
        }
        runner_calls = len(project.runner.calls)
        for kind, envelope in envelopes.items():
            assert orchestrator.accept(kind, envelope) == "no-op", kind
        assert len(project.runner.calls) == runner_calls, \
            "compile/list не должны повторяться при no-op"

    @allure.title("Implementation no-op не запускает compile/list")
    def test_impl_repeat_skips_checks(self, project):
        orchestrator = project.drive_to_implementation_ready()
        compiles = project.runner.count(
            lambda argv: len(argv) > 1
            and argv[1] == "tools/compile-tests.sh")
        assert orchestrator.accept(
            "implementation", project.impl_envelope()) == "no-op"
        assert project.runner.count(
            lambda argv: len(argv) > 1
            and argv[1] == "tools/compile-tests.sh") == compiles

    @allure.title("Реальный дрейф документа при повторе блокируется")
    def test_repeat_with_drift_blocked(self, project):
        orchestrator = project.orchestrator()
        project.init(orchestrator)
        envelope = project.context_envelope()
        assert orchestrator.accept("context", envelope) == "accepted"
        (project.root / "docs/context.json").write_text(
            '{"schema_version":2}\n')
        with pytest.raises(WorkflowBlockedError):
            orchestrator.accept("context", envelope)

    @allure.title("Изменённый payload того же вида на ревизии — 69")
    def test_changed_payload_blocked(self, project):
        orchestrator = project.orchestrator()
        project.init(orchestrator)
        orchestrator.accept("context", project.context_envelope())
        sources = project.context_sources()[:1]
        changed = project.envelope("context", {"sources": sources},
                                   name="context-changed.json")
        with pytest.raises(WorkflowBlockedError):
            orchestrator.accept("context", changed)


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("Локальная TestOps-цепочка: sent → verify без повторов")
@allure.severity(allure.severity_level.BLOCKER)
class TestLocalTestOpsChain:
    def _results_dir(self, project):
        return project.root / "artifacts" / "harness" / \
            C.EXECUTION_HEAD / "allure-results"

    @allure.title("plan → assign → package → upload → verify до uploaded")
    def test_full_local_chain(self, project):
        orchestrator = _to_executed(project)
        utils.testops_local_handlers(
            project.runner, project.root, C.EXECUTION_HEAD,
            self._results_dir(project), dict(C.BINDINGS))
        with allure.step("prepare-testops: plan/assign/package"):
            outcome = orchestrator.prepare_testops(C.EXECUTION_HEAD)
        assert outcome["outcome"] == "prepared"
        with allure.step("publish-testops: upload + verify"):
            outcome = orchestrator.publish_testops(
                C.EXECUTION_HEAD, execute=True)
        assert outcome["outcome"] == "uploaded"

    @allure.title("Crash после sent: verify возобновляется без re-upload")
    def test_sent_to_verify_resume(self, project):
        orchestrator = _to_executed(project)
        utils.testops_local_handlers(
            project.runner, project.root, C.EXECUTION_HEAD,
            self._results_dir(project), dict(C.BINDINGS))
        outcome = orchestrator.prepare_testops(C.EXECUTION_HEAD)
        assert outcome["outcome"] == "prepared"

        def crash_after_verify_call(argv, line):
            raise RuntimeError("orchestrator died after upload sent")
        utils.on_testops(project.runner, "verify",
                         crash_after_verify_call)
        with allure.step("publish: upload дошёл (sent), краш на verify"):
            outcome = orchestrator.publish_testops(
                C.EXECUTION_HEAD, execute=True)
        assert outcome["exit"] == 75
        uploads = [argv for argv in
                   project.runner.tool_calls("tools/run-testops.sh")
                   if "upload" in argv]
        assert len(uploads) == 1
        with allure.step("Повторный publish заблокирован decide_upload"):
            with pytest.raises(WorkflowBlockedError):
                orchestrator.publish_testops(C.EXECUTION_HEAD,
                                             execute=True)
        assert len([argv for argv in
                    project.runner.tool_calls("tools/run-testops.sh")
                    if "upload" in argv]) == 1
        utils.testops_local_handlers(
            project.runner, project.root, C.EXECUTION_HEAD,
            self._results_dir(project), dict(C.BINDINGS))
        with allure.step("verify-testops возобновляет с sent → uploaded"):
            outcome = orchestrator.verify_testops(
                C.EXECUTION_HEAD, online=True)
        assert outcome["outcome"] == "uploaded"
        uploads = [argv for argv in
                   project.runner.tool_calls("tools/run-testops.sh")
                   if "upload" in argv]
        assert len(uploads) == 1, "повторная отправка недопустима"

    @allure.title("verify-testops без sent/uploaded блокируется")
    def test_verify_requires_sent(self, project):
        orchestrator = _to_executed(project)
        utils.make_testops_state(project.root, C.EXECUTION_HEAD,
                                 upload_status="pending")
        with pytest.raises(WorkflowBlockedError):
            orchestrator.verify_testops(C.EXECUTION_HEAD, online=True)

    @allure.title("uploaded: verify — no-op, транспорта нет")
    def test_verify_uploaded_noop(self, project):
        orchestrator = _to_executed(project)
        utils.make_testops_state(project.root, C.EXECUTION_HEAD,
                                 upload_status="uploaded", launch_id=91)
        outcome = orchestrator.verify_testops(C.EXECUTION_HEAD,
                                              online=True)
        assert outcome["outcome"] == "no-op"
        verify_calls = [argv for argv in
                        project.runner.tool_calls("tools/run-testops.sh")
                        if "verify" in argv]
        assert verify_calls == []
