"""Intents, TestOps-гарды и PR-модель: отсутствие дублей внешних операций."""
import allure
import pytest

from infrastructure.workflow import adapters
from infrastructure.workflow import state as state_mod
from infrastructure.workflow.state import (
    WorkflowBlockedError, WorkflowPermissionError)
from test_data.consts import workflow as C
from test_data.utils import workflow as utils


@pytest.fixture
def project(tmp_path):
    return utils.Project(tmp_path / "proj")


def _state(project):
    state_dir = next(
        path for path in project.store_dir.iterdir()
        if path.is_dir() and state_mod.WORKFLOW_ID_RE.fullmatch(path.name))
    return state_mod.load_state(state_dir)


def _to_executed(project):
    """implementation_ready + записанный head/base execution -> executed."""
    orchestrator = project.drive_to_executed()
    state = _state(project)
    assert state["phase"] == "executed"
    return orchestrator, state


def _to_commit_executed(project):
    """Commit-head + clean tests fixture до executed для PR-проверок."""
    orchestrator = project.drive_commit_to_executed()
    state = _state(project)
    assert state["phase"] == "executed"
    return orchestrator, state


def _pr_spec(project, role="app"):
    orchestrator = project.orchestrator()
    orchestrator.pr_prepare(role, title="unit PR", head_branch="wf/head",
                            base_branch="main")
    return _state(project)["publications"]["pr"][role]["spec"]


def _publish_handlers(project):
    """Fake TestOps CLI: upload помечает sent, verify — uploaded."""
    project.publish_handlers()


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("TestOps: гард перед транспортом, без повторов")
@allure.severity(allure.severity_level.BLOCKER)
class TestTestOpsGuards:
    @allure.title("publish без --execute отклоняется до любого вызова")
    def test_permission_required(self, project):
        orchestrator, _ = _to_executed(project)
        utils.make_testops_state(project.root, C.EXECUTION_HEAD)
        with pytest.raises(WorkflowPermissionError):
            orchestrator.publish_testops(C.EXECUTION_HEAD)
        assert project.runner.tool_calls("tools/run-testops.sh") == []

    @allure.title("M12: sent/unknown/in_progress/uploaded блокируют upload")
    @pytest.mark.parametrize("status",
                             ("sent", "unknown", "in_progress", "uploaded"))
    def test_indeterminate_statuses_block(self, project, status):
        orchestrator, _ = _to_executed(project)
        utils.make_testops_state(project.root, C.EXECUTION_HEAD,
                                 upload_status=status, launch_id=77)
        with pytest.raises(WorkflowBlockedError):
            orchestrator.publish_testops(C.EXECUTION_HEAD, execute=True)
        assert project.runner.tool_calls("tools/run-testops.sh") == []

    @allure.title("Execution state вне workflow executions отклоняется")
    def test_unrecorded_execution(self, project):
        orchestrator, _ = _to_executed(project)
        utils.make_testops_state(project.root, C.EXECUTION_OTHER)
        with pytest.raises(WorkflowBlockedError):
            orchestrator.publish_testops(C.EXECUTION_OTHER, execute=True)

    @allure.title("M9: dispatch→crash→reconcile; повторный upload не уходит")
    def test_crash_after_upload_no_resend(self, project):
        orchestrator, _ = _to_executed(project)
        utils.make_testops_state(project.root, C.EXECUTION_HEAD)

        def crash_after_write(argv, _on_line):
            utils.set_upload_status(project.root, C.EXECUTION_HEAD, "sent",
                                    launch_id=88)
            raise RuntimeError("process died after external write")
        utils.on_testops(project.runner, "upload", crash_after_write)

        with allure.step("Upload dispatch и падение до save"):
            outcome = orchestrator.publish_testops(C.EXECUTION_HEAD,
                                                   execute=True)
        assert outcome["exit"] == 75
        state = _state(project)
        intent = state_mod.unfinished_intents(state)[0]
        assert intent["operation"] == "testops.upload"

        with allure.step("Reconcile принимает sent из execution state"):
            report = project.orchestrator().reconcile()
        assert report[0]["action"] == "adopted"

        with allure.step("Повторный publish заблокирован до транспорта"):
            with pytest.raises(WorkflowBlockedError):
                project.orchestrator().publish_testops(
                    C.EXECUTION_HEAD, execute=True)
        uploads = [argv for argv in
                   project.runner.tool_calls("tools/run-testops.sh")
                   if "upload" in argv]
        assert len(uploads) == 1, "второй upload недопустим"

    @allure.title("M13: неудачный upload не триггерит новый запуск API")
    def test_failed_upload_no_rerun(self, project):
        orchestrator, _ = _to_executed(project)
        utils.make_testops_state(project.root, C.EXECUTION_HEAD)
        utils.on_testops(project.runner, "upload", utils.ok_lines([], 1))
        before = len(project.runner.tool_calls("tools/run-tests.sh"))
        outcome = orchestrator.publish_testops(C.EXECUTION_HEAD,
                                               execute=True)
        assert outcome["exit"] == 75
        assert len(project.runner.tool_calls("tools/run-tests.sh")) == before

    @allure.title("Подтверждённый upload фиксирует публикацию по execution")
    def test_successful_upload(self, project):
        orchestrator, _ = _to_executed(project)
        _publish_handlers(project)
        outcome = orchestrator.publish_testops(C.EXECUTION_HEAD,
                                               execute=True)
        assert outcome["outcome"] == "uploaded"
        state = _state(project)
        obs = state["publications"]["testops"]["last_observation"]
        assert obs["upload_status"] == "uploaded"
        assert state["phase"] == "executed"  # PR ещё не подтверждены


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("Run-execution: intent без слепого повтора")
@allure.severity(allure.severity_level.BLOCKER)
class TestRunIntents:
    @allure.title("M12: undetermined head-run никогда не запускается повторно")
    def test_undetermined_run_not_repeated(self, project):
        orchestrator = project.drive_to_implementation_ready()

        def die(argv, _line):
            raise RuntimeError("runner crashed mid-run")
        utils.harness_run(project.runner, project.root, "unused",
                          C.HEAD_JUNIT, 0)
        project.runner.add(
            lambda argv: "group" in argv, die)
        outcome = orchestrator.run_execution("head")
        assert outcome["exit"] == 75
        before = sum(1 for argv in project.runner.calls if "group" in argv)
        with pytest.raises(WorkflowBlockedError):
            project.orchestrator().run_execution("head")
        assert sum(1 for argv in project.runner.calls
                   if "group" in argv) == before

    @allure.title("M4: crash после evidence до save — reconcile усваивает run")
    def test_evidence_adopted_on_reconcile(self, project):
        orchestrator = project.drive_to_implementation_ready()
        evidence = utils.write_manifest(
            project.root, C.EXECUTION_HEAD, C.HEAD_JUNIT, 0,
            declared={"app_base_sha": C.APP_BASE_SHA,
                      "app_patch_sha256": C.APP_PATCH_SHA256})

        state_dir = project.store_dir
        workflow_dir = next(p for p in state_dir.iterdir() if p.is_dir())
        state = state_mod.load_state(workflow_dir)
        intent = state_mod.new_intent(state, "run.execution",
                                      {"variant": "head"})
        intent["status"] = "dispatched"
        intent["evidence"] = {"evidence_dir": str(evidence)}
        state_mod.save_state(workflow_dir, state)

        report = orchestrator.reconcile()
        assert report[0]["action"] == "adopted"
        state = _state(project)
        assert any(e["execution_id"] == C.EXECUTION_HEAD
                   for e in state["executions"])

    @allure.title("Новый прогон получает новый execution_id, старый цел")
    def test_new_execution_distinct(self, project):
        orchestrator = project.drive_to_implementation_ready()
        utils.harness_run(project.runner, project.root, C.EXECUTION_HEAD,
                          C.HEAD_JUNIT, 0,
                          declared={"app_base_sha": C.APP_BASE_SHA,
                                    "app_patch_sha256": C.APP_PATCH_SHA256})
        orchestrator.run_execution("head")
        utils.write_manifest(project.root, C.EXECUTION_OTHER, C.HEAD_JUNIT,
                             0, declared={
                                 "app_base_sha": C.APP_BASE_SHA,
                                 "app_patch_sha256": C.APP_PATCH_SHA256})
        orchestrator.import_execution(C.EXECUTION_OTHER)
        state = _state(project)
        ids = [e["execution_id"] for e in state["executions"]]
        assert set(ids) == {C.EXECUTION_HEAD, C.EXECUTION_OTHER}

    @allure.title("Краш до dispatch: declared intent переиспользуется")
    def test_declared_intent_reused(self, project):
        orchestrator = project.drive_to_implementation_ready()
        state_dir = next(p for p in project.store_dir.iterdir()
                         if p.is_dir())
        state = state_mod.load_state(state_dir)
        intent = state_mod.new_intent(state, "run.execution",
                                      {"variant": "head"})
        state_mod.save_state(state_dir, state)
        utils.harness_run(project.runner, project.root, C.EXECUTION_HEAD,
                          C.HEAD_JUNIT, 0,
                          declared={"app_base_sha": C.APP_BASE_SHA,
                                    "app_patch_sha256": C.APP_PATCH_SHA256})
        outcome = orchestrator.run_execution("head")
        assert outcome["outcome"] == "recorded"
        state = _state(project)
        run_intents = [i for i in state["intents"]
                       if i["operation"] == "run.execution"]
        assert len(run_intents) == 1
        assert run_intents[0]["intent_id"] == intent["intent_id"]

    @allure.title("unit-прогон не удовлетворяет api-gate")
    def test_unit_scope_not_satisfying(self, project):
        orchestrator = project.drive_to_implementation_ready()
        utils.write_manifest(project.root, C.EXECUTION_HEAD,
                             C.UNIT_JUNIT_SAME_COUNTS, 0,
                             targets=("tests/unit",),
                             declared={"app_base_sha": C.APP_BASE_SHA,
                                       "app_patch_sha256":
                                           C.APP_PATCH_SHA256})
        orchestrator.import_execution(C.EXECUTION_HEAD)
        state = _state(project)
        assert state["phase"] == "implementation_ready"


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("Импорт принятого execution — read-only")
@allure.severity(allure.severity_level.BLOCKER)
class TestImportExecution:
    @allure.title("M14: uploaded execution импортируется, источник не меняется")
    def test_imported_uploaded_readonly(self, project):
        orchestrator = project.drive_to_implementation_ready()
        results_dir = utils.write_manifest(
            project.root, C.EXECUTION_BASE, C.BASE_JUNIT, 1,
            declared={"app_base_sha": C.APP_BASE_SHA}) / "allure-results"
        utils.make_testops_state(
            project.root, C.EXECUTION_BASE, upload_status="uploaded",
            launch_id=99, results_dir=results_dir)
        before = utils.testops_state_sha(project.root, C.EXECUTION_BASE)
        outcome = orchestrator.import_execution(C.EXECUTION_BASE)
        assert outcome["outcome"] == "imported"
        state = _state(project)
        entry = next(e for e in state["executions"]
                     if e["execution_id"] == C.EXECUTION_BASE)
        assert entry["source"] == "imported"
        assert entry["bound_revision"] == 1
        assert utils.testops_state_sha(
            project.root, C.EXECUTION_BASE) == before

    @allure.title("Импорт повреждённого package отклоняется до записи")
    def test_import_corrupt_package(self, project):
        orchestrator = project.drive_to_implementation_ready()
        utils.write_manifest(project.root, C.EXECUTION_BASE,
                             C.BASE_JUNIT, 1,
                             declared={"app_base_sha": C.APP_BASE_SHA})
        results_dir = project.root / "artifacts" / "harness" / \
            C.EXECUTION_BASE / "allure-results"
        utils.make_testops_state(project.root, C.EXECUTION_BASE,
                                 upload_status="uploaded", launch_id=55,
                                 results_dir=results_dir)
        (results_dir / "extra.json").write_text("mutated")
        with pytest.raises(WorkflowBlockedError):
            orchestrator.import_execution(C.EXECUTION_BASE)

    @allure.title("20R: base-прогон чужого base_sha отклоняется, не bound=0")
    def test_foreign_base_not_bound(self, project):
        orchestrator = project.drive_to_implementation_ready()
        utils.write_manifest(project.root, C.EXECUTION_BASE,
                             C.BASE_JUNIT, 1,
                             declared={"app_base_sha": C.APP_BASE_SHA_2})
        outcome = orchestrator.import_execution(C.EXECUTION_BASE)
        assert outcome["outcome"] == "blocked"
        state = _state(project)
        assert not any(e["execution_id"] == C.EXECUTION_BASE
                       for e in state["executions"])
        assert state["phase"] == "implementation_ready"


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("PR-модель: свежий поиск перед create, без дублей")
@allure.severity(allure.severity_level.BLOCKER)
class TestPrModel:
    def _make_ref(self, spec, number=7):
        return adapters.PrRef(repo=spec["repo"], number=number,
                              url="https://git.invalid/pr/7",
                              title=spec["title"],
                              head_branch=spec["head_branch"],
                              base_branch=spec["base_branch"],
                              head_sha=spec.get("head_sha"),
                              body_sha256=spec.get("body_sha256"),
                              files=list(spec.get("files") or []))

    def _transport(self, spec, *, search=None, get=True):
        ref = self._make_ref(spec)
        return adapters.FakePrTransport(
            search_result=[] if search is None else search,
            create_result=ref,
            get_map={(spec["repo"], ref.number): ref} if get else {})

    @allure.title("M10: create→crash→reconcile усваивает ровно один PR")
    def test_create_crash_adopt_not_duplicate(self, project):
        orchestrator, _ = _to_commit_executed(project)
        spec = _pr_spec(project)
        ref = self._make_ref(spec)
        calls = {"create": 0}

        def dying_create(spec_arg):
            calls["create"] += 1
            raise RuntimeError("process died after the remote write")
        transport = adapters.FakePrTransport(
            # Сервер «видит» PR только после того, как create был вызван:
            # до dispatch поиск обязан вернуть пусто.
            search_result=lambda key: [ref] if calls["create"] else [],
            create_result=dying_create,
            get_map={(spec["repo"], ref.number): ref})
        orch = project.orchestrator(pr_transports={"app": transport})
        with allure.step("Dispatch create и падение до save"):
            outcome = orch.pr_create("app", execute=True, online=True)
        assert outcome["exit"] == 75
        with allure.step("Reconcile находит ровно один PR и усваивает его"):
            report = orch.reconcile(online=True)
        assert report[0]["action"] == "adopted"
        assert calls["create"] == 1, "второй create недопустим"
        outcome = orch.pr_create("app", execute=True, online=True)
        assert outcome["outcome"] == "no-op"
        assert calls["create"] == 1

    @allure.title("20R: unknown-исход create не снимается пустым поиском")
    def test_unknown_then_zero_search_stays_blocked(self, project):
        _to_commit_executed(project)
        spec = _pr_spec(project)
        ref = self._make_ref(spec)
        found = {"prs": []}
        transport = adapters.FakePrTransport(
            search_result=lambda key: list(found["prs"]),
            create_result=lambda s: (found["prs"].append(ref), ref)[1],
            get_map={(spec["repo"], ref.number): ref})
        state_dir = next(p for p in project.store_dir.iterdir()
                         if p.is_dir())
        state = state_mod.load_state(state_dir)
        intent = state_mod.new_intent(state, "pr.create",
                                      {"repo": "app",
                                       "spec_sha256": spec["spec_sha256"],
                                       "spec": dict(spec)})
        intent["status"] = "dispatched"
        state["publications"]["pr"]["app"]["status"] = "intent"
        state["publications"]["pr"]["app"]["intent_id"] = \
            intent["intent_id"]
        state_mod.save_state(state_dir, state)

        orch = project.orchestrator(pr_transports={"app": transport})
        with allure.step("Пока intent не разрешён, create запрещён"):
            outcome = orch.pr_create("app", execute=True, online=True)
        assert outcome["exit"] == 69
        with allure.step("Reconcile со свежим поиском 0 — blocked; "
                         "intent остаётся unresolved, не failed"):
            report = orch.reconcile(online=True)
        assert report[0]["action"] == "blocked"
        state = _state(project)
        assert state["intents"][-1]["status"] in \
            state_mod.UNFINISHED_INTENT_STATUSES
        assert state["publications"]["pr"]["app"]["status"] == "blocked"
        with allure.step("Re-prepare не стирает unresolved-эффект"):
            outcome = orch.pr_prepare("app", title="unit PR v2",
                                      head_branch="wf/head",
                                      base_branch="main")
        assert outcome["outcome"] == "blocked"
        with allure.step("Create по-прежнему запрещён, повторов нет"):
            outcome = orch.pr_create("app", execute=True, online=True)
        assert outcome["outcome"] == "blocked"
        assert not [n for n, _ in transport.calls if n == "create"]

    @allure.title("M11: неполные/чужие/множественные результаты блокируют")
    @pytest.mark.parametrize("found_kind", ("incomplete", "foreign",
                                            "multiple"))
    def test_ambiguous_search_blocks(self, project, found_kind):
        _to_commit_executed(project)
        spec = _pr_spec(project)
        ref = self._make_ref(spec, number=3)
        if found_kind == "incomplete":
            found = [adapters.PrRef(repo=spec["repo"], number=3)]
        elif found_kind == "foreign":
            found = [adapters.PrRef(repo="other/repo", number=9,
                                    title=spec["title"],
                                    head_branch=spec["head_branch"],
                                    base_branch=spec["base_branch"])]
        else:
            found = [self._make_ref(spec, 3), self._make_ref(spec, 4)]
        transport = adapters.FakePrTransport(
            search_result=found, create_result=ref,
            get_map={(spec["repo"], ref.number): ref})
        orch = project.orchestrator(pr_transports={"app": transport})
        outcome = orch.pr_create("app", execute=True, online=True)
        assert outcome.get("exit") == 69
        assert not any(name == "create" for name, _ in transport.calls)

    @allure.title("Один точный match усваивается без create")
    def test_exact_match_adopted(self, project):
        _to_commit_executed(project)
        spec = _pr_spec(project)
        ref = self._make_ref(spec, number=12)
        transport = adapters.FakePrTransport(
            search_result=[ref], create_result=ref,
            get_map={(spec["repo"], 12): ref})
        orch = project.orchestrator(pr_transports={"app": transport})
        outcome = orch.pr_create("app", execute=True, online=True)
        assert outcome["outcome"] == "adopted"
        assert not any(name == "create" for name, _ in transport.calls)

    @allure.title("Без транспорта PR-операции — 77")
    def test_no_transport_permission(self, project):
        orchestrator, _ = _to_commit_executed(project)
        _pr_spec(project)
        with pytest.raises(WorkflowPermissionError):
            orchestrator.pr_create("app", execute=True, online=True)
        with pytest.raises(WorkflowPermissionError):
            orchestrator.pr_search("app", online=True)

    @allure.title("App и tests PR — раздельные записи")
    def test_separate_pr_entries(self, project):
        orchestrator, _ = _to_commit_executed(project)
        _publish_handlers(project)
        orchestrator.publish_testops(C.EXECUTION_HEAD, execute=True)
        for role in ("app", "tests"):
            spec = _pr_spec(project, role)
            transport = self._transport(spec)
            orch = project.orchestrator(
                pr_transports={role: transport})
            outcome = orch.pr_create(role, execute=True, online=True)
            assert outcome["outcome"] == "verified"
        state = _state(project)
        assert state["phase"] == "published"
        assert state["publications"]["pr"]["app"]["number"] == 7
        assert state["publications"]["pr"]["tests"]["number"] == 7
