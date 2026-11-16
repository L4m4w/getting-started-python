"""Сквозные проверки: lock'и, границы краша, терминальные повторы, CLI."""
import json
import subprocess
import sys
import threading
from pathlib import Path

import allure
import pytest

from infrastructure.reporting.testops.lifecycle import LockHeldError
from infrastructure.workflow import state as state_mod
from infrastructure.workflow.locks import WorkflowLock
from infrastructure.workflow.state import (
    WorkflowBlockedError, WorkflowStateCorruptError)
from test_data.consts import workflow as C
from test_data.consts import workflow_tests_repo as RC
from test_data.utils import workflow as utils


@pytest.fixture
def project(tmp_path):
    return utils.Project(tmp_path / "proj")


def _workflow_dir(project):
    return next(
        path for path in project.store_dir.iterdir()
        if path.is_dir()
        and state_mod.WORKFLOW_ID_RE.fullmatch(path.name))


def _drive_to_published(project):
    orchestrator = project.drive_commit_to_executed()
    project.publish_handlers()
    outcome = orchestrator.publish_testops(C.EXECUTION_HEAD, execute=True)
    assert outcome["outcome"] == "uploaded"
    transports = {role: project.fake_pr_for(role) for role in ("app",
                                                             "tests")}
    orch = project.orchestrator(pr_transports=transports)
    for role in ("app", "tests"):
        files = ([C.CHANGED_APP_FILE] if role == "app" else [])
        orch.pr_prepare(role, title="unit PR", head_branch="wf/head",
                        base_branch="main", files=files)
        outcome = orch.pr_create(role, execute=True, online=True)
        assert outcome["outcome"] == "verified", outcome
    state = project.workflow_state()
    assert state["phase"] == "published"
    return orch, transports, state


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("Блокировки: один writer на workflow и index")
@allure.severity(allure.severity_level.BLOCKER)
class TestLocking:
    @allure.title("M8: второй writer отклоняется, пока lock удерживается")
    def test_concurrent_writer_refused(self, project):
        orchestrator = project.orchestrator()
        project.init(orchestrator)
        workflow_dir = _workflow_dir(project)
        entered = threading.Event()
        release = threading.Event()

        def holder():
            with WorkflowLock(workflow_dir, operation="concurrent"):
                entered.set()
                release.wait(timeout=10)
        thread = threading.Thread(target=holder)
        thread.start()
        try:
            assert entered.wait(timeout=5)
            with pytest.raises(LockHeldError):
                WorkflowLock(workflow_dir,
                             operation="contender").acquire()
            with pytest.raises(WorkflowBlockedError):
                orchestrator.accept("context", project.context_envelope())
        finally:
            release.set()
            thread.join(timeout=10)

    @allure.title("Lock мёртвого pid освобождается как мьютекс")
    def test_dead_pid_lock_reclaimed(self, project):
        orchestrator = project.orchestrator()
        project.init(orchestrator)
        workflow_dir = _workflow_dir(project)
        (workflow_dir / "workflow.lock").write_text(json.dumps(
            {"pid": 2 ** 22, "token": "dead", "operation": "stale",
             "acquired_at": "2026-01-01T00:00:00+00:00"}))
        with WorkflowLock(workflow_dir, operation="reclaim"):
            pass  # не упали: reclaim удалил мёртвый lock
        outcome = orchestrator.accept("context", project.context_envelope())
        assert outcome == "accepted"

    @allure.title("Битый lock-файл отклоняется явно")
    def test_corrupt_lock_refused(self, project):
        orchestrator = project.orchestrator()
        project.init(orchestrator)
        workflow_dir = _workflow_dir(project)
        (workflow_dir / "workflow.lock").write_text("{garbage")
        with pytest.raises(WorkflowBlockedError):
            orchestrator.accept("context", project.context_envelope())

    @allure.title("M8: второй writer index отклоняется до state")
    def test_index_lock_contention(self, project):
        from infrastructure.workflow import index as index_mod
        project.store_dir.mkdir(parents=True, exist_ok=True)
        entered = threading.Event()
        release = threading.Event()

        def holder():
            with index_mod.acquire(project.store_dir):
                entered.set()
                release.wait(timeout=10)
        thread = threading.Thread(target=holder)
        thread.start()
        try:
            assert entered.wait(timeout=5)
            with pytest.raises(WorkflowBlockedError):
                project.init()
        finally:
            release.set()
            thread.join(timeout=10)
        assert not list(project.store_dir.glob("wf-*/state.json"))


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("Границы краша между index и state")
@allure.severity(allure.severity_level.BLOCKER)
class TestCrashBoundaries:
    @allure.title("M17: crash после register до state — та же линия, не дубль")
    def test_index_without_state_resumes(self, project):
        from infrastructure.workflow import index as index_mod
        store = project.store_dir
        store.mkdir(parents=True)
        workflow_id = state_mod.workflow_id_for(
            C.PILOT_ID, C.APP_REPO_KEY, C.APP_BASE_SHA)
        with index_mod.acquire(store):
            index = index_mod.new_index()
            index_mod.register(index, C.APP_REPO_KEY, C.PILOT_ID,
                               workflow_id, C.APP_BASE_SHA,
                               status="creating")
            index_mod.save_index(store, index)
        # "Краш": state.json так и не записан
        workflow_id2, outcome = project.init()
        assert workflow_id2 == workflow_id and outcome == "created"
        dirs = [p.name for p in store.iterdir() if p.is_dir()]
        assert dirs == [workflow_id]

    @allure.title("M17: повреждённый state блокирует всё, файл не тронут")
    def test_corrupt_state_byte_identical(self, project):
        orchestrator = project.orchestrator()
        project.init(orchestrator)
        workflow_dir = _workflow_dir(project)
        state_path = state_mod.state_path(workflow_dir)
        state_path.write_text("{corrupt-state")
        before = state_path.read_bytes()
        for action in (lambda: orchestrator.status(),
                       lambda: orchestrator.accept(
                           "context", project.context_envelope()),
                       lambda: orchestrator.reconcile(),
                       lambda: orchestrator.resume()):
            with pytest.raises(WorkflowStateCorruptError):
                action()
            assert state_path.read_bytes() == before

    @allure.title("M17: схема чужой версии не перезаписывается")
    def test_foreign_schema_untouched(self, project):
        orchestrator = project.orchestrator()
        project.init(orchestrator)
        workflow_dir = _workflow_dir(project)
        state_path = state_mod.state_path(workflow_dir)
        original = json.loads(state_path.read_text())
        original["workflow_schema_version"] = 7
        state_path.write_text(json.dumps(original))
        before = state_path.read_bytes()
        with pytest.raises(WorkflowStateCorruptError):
            orchestrator.status()
        assert state_path.read_bytes() == before

    @allure.title("status/resume не создают state из воздуха")
    def test_no_silent_state_creation(self, project):
        orchestrator = project.orchestrator()
        with pytest.raises(WorkflowBlockedError):
            orchestrator.status()
        with pytest.raises(WorkflowBlockedError):
            orchestrator.reconcile()
        assert not project.store_dir.exists() or not list(
            project.store_dir.iterdir())


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("Полный оффлайн-прогон до published и обратно")
@allure.severity(allure.severity_level.BLOCKER)
class TestEndToEnd:
    @allure.title("M4: вся цепочка фаз до published с фейк-транспортами")
    def test_full_chain_to_published(self, project):
        _drive_to_published(project)
        state = project.workflow_state()
        assert state["phase"] == "published"
        assert state["publications"]["testops"]["last_observation"][
            "upload_status"] == "uploaded"

    @allure.title("M18: повтор после published — no-op без транспортов")
    def test_terminal_repeat_no_transport(self, project):
        orch, transports, _ = _drive_to_published(project)
        calls_before = {role: len(t.calls) for role, t in transports.items()}
        runner_before = len(project.runner.calls)
        with allure.step("Повторный init тем же входом — resumed"):
            _, outcome = project.init(
                orch, app_head_kind="commit",
                app_head_git_sha=C.APP_HEAD_COMMIT_SHA,
                app_head_sha256=None)
            assert outcome == "resumed"
        with allure.step("publish-testops — no-op, transport не вызван"):
            outcome = orch.publish_testops(C.EXECUTION_HEAD, execute=True)
            assert outcome["outcome"] == "no-op"
        with allure.step("pr create — no-op"):
            for role in ("app", "tests"):
                outcome = orch.pr_create(role, execute=True, online=True)
                assert outcome["outcome"] == "no-op"
        uploads = [a for a in project.runner.tool_calls(
            "tools/run-testops.sh") if "upload" in a]
        assert len(project.runner.calls) == runner_before
        assert {r: len(t.calls) for r, t in transports.items()} == \
            calls_before

    @allure.title("M18+20R: accept после published — no-op копия, дрейф 69")
    def test_published_rejects_plain_accept(self, project):
        orch, _, _ = _drive_to_published(project)
        with allure.step("Идентичный принятый артефакт — no-op в любой фазе"):
            assert orch.accept("context", project.context_envelope()) \
                == "no-op"
        with allure.step("Изменённый артефакт на той же ревизии — 69"):
            other = project.envelope(
                "context", {"sources": project.context_sources()},
                name="context-other.json", document={
                    "path": "docs/context.json",
                    "sha256": "0" * 64})
            with pytest.raises(WorkflowBlockedError):
                orch.accept("context", other)

    @allure.title("resume после published сообщает терминальность")
    def test_resume_terminal(self, project):
        orch, _, _ = _drive_to_published(project)
        report = orch.resume()
        assert report["next_step"] == "terminal: nothing to do"


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("CLI: коды выхода и surface")
@allure.severity(allure.severity_level.CRITICAL)
class TestCli:
    def _cli(self, project, *args):
        repo = Path(__file__).resolve().parents[2]
        argv = [sys.executable, str(repo / "tools" / "workflow.py"),
                "--store-dir", str(project.store_dir), *args]
        return subprocess.run(argv, cwd=project.root,
                              capture_output=True, text=True, timeout=60)

    @allure.title("init через CLI: выход 0 и печать workflow_id")
    def test_cli_init(self, project):
        result = self._cli(
            project, "init", "--pilot-id", C.PILOT_ID, "--app-repo",
            C.APP_REPO, "--app-base-sha", C.APP_BASE_SHA,
            "--app-patch-sha256", C.APP_PATCH_SHA256,
            "--tests-commit", C.TESTS_COMMIT, "--tests-clean",
            "--tests-repo", RC.TESTS_REPO,
            "--requirements", str(project.root / C.REQUIREMENTS_REL))
        assert result.returncode == 0, result.stderr
        assert "wf-" in result.stdout

    @allure.title("Ошибки входа CLI дают 69, а не traceback")
    def test_cli_validation_exit(self, project):
        result = self._cli(
            project, "init", "--pilot-id", C.PILOT_ID, "--app-repo",
            C.APP_REPO, "--app-base-sha", "0000",
            "--app-patch-sha256", C.APP_PATCH_SHA256,
            "--tests-commit", C.TESTS_COMMIT, "--tests-clean",
            "--tests-repo", RC.TESTS_REPO,
            "--requirements", str(project.root / C.REQUIREMENTS_REL))
        assert result.returncode == 69
        assert result.stdout == ""
