"""Init/accept-фаза оркестратора: идемпотентность, gate'ы и валидация."""
import json
from pathlib import Path

import allure
import pytest

from infrastructure.workflow import index as index_mod
from infrastructure.workflow import state as state_mod
from infrastructure.workflow.state import (
    WorkflowBlockedError, WorkflowValidationError)
from test_data.consts import workflow as C
from test_data.utils import workflow as utils


@pytest.fixture
def project(tmp_path):
    return utils.Project(tmp_path / "proj")


def _load(project):
    state_dir = next(
        path for path in project.store_dir.iterdir()
        if path.is_dir() and state_mod.WORKFLOW_ID_RE.fullmatch(path.name))
    return state_mod.load_state(state_dir), state_dir


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("Init и детерминированная идентичность")
@allure.severity(allure.severity_level.CRITICAL)
class TestInit:
    @allure.title("M1: повторный init с тем же входом — resume без reset")
    def test_repeated_init_resumes(self, project):
        with allure.step("Первый init"):
            first_id, outcome = project.init()
        assert outcome == "created"
        with allure.step("Повторный init тем же входом"):
            second_id, outcome = project.init()
        assert second_id == first_id and outcome == "resumed"
        state, _ = _load(project)
        events = [entry["event"] for entry in state["journal"]]
        assert events.count("init") == 1 and "resumed" in events

    @allure.title("M2: новый base под тем же repo+pilot блокируется")
    def test_conflicting_base_blocked(self, project):
        project.init()
        with pytest.raises(WorkflowBlockedError):
            project.init(app_base_sha=C.APP_BASE_SHA_2)
        dirs = [p.name for p in project.store_dir.iterdir() if p.is_dir()]
        assert len(dirs) == 1, "обход журнала новым workflow запрещён"

    @allure.title("M2: --supersede создаёт связанный workflow")
    def test_supersede_links(self, project):
        old_id, _ = project.init()
        new_id, outcome = project.init(app_base_sha=C.APP_BASE_SHA_2,
                                       supersede=True)
        assert outcome == "created" and new_id != old_id
        state = state_mod.load_state(project.store_dir / new_id)
        assert state["supersedes"] == old_id
        index = index_mod.load_index(project.store_dir)
        entry = index_mod.find_entry(index, C.APP_REPO_KEY, C.PILOT_ID)
        assert entry["workflow_id"] == new_id
        assert old_id in (entry.get("superseded") or [])

    @allure.title("Невалидные SHA входа отклоняются строго")
    def test_invalid_sha_rejected(self, project):
        with pytest.raises(WorkflowValidationError):
            project.init(app_base_sha="0000")
        with pytest.raises(WorkflowValidationError):
            project.init(app_head_sha256="0000")
        with pytest.raises(WorkflowValidationError):
            project.init(tests_commit="not-a-sha")

    @allure.title("kind=commit без git_sha и kind=patch без sha256 невалидны")
    def test_head_kind_values(self, project):
        with pytest.raises(WorkflowValidationError):
            project.init(app_head_kind="commit", app_head_git_sha=None)
        with pytest.raises(WorkflowValidationError):
            project.init(app_head_kind="patch", app_head_sha256=None)

    @allure.title("pilot_id вне домена отклоняется")
    def test_bad_pilot(self, project):
        with pytest.raises(WorkflowValidationError):
            project.init(pilot_id="bad pilot!")

    @allure.title("Отсутствующий файл требований отклоняется")
    def test_missing_requirements(self, project):
        with pytest.raises(WorkflowValidationError):
            project.init(requirements_path="docs/missing.md")


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("Accept: порядок фаз и валидация envelope")
@allure.severity(allure.severity_level.CRITICAL)
class TestAccept:
    @allure.title("Полная цепочка фаз до implementation_ready")
    def test_phase_chain(self, project):
        orchestrator = project.drive_to_implementation_ready()
        state, _ = _load(project)
        assert state["phase"] == "implementation_ready"
        for kind in state_mod.ARTIFACT_KINDS:
            assert state["artifacts"][kind]["status"] == "pending" \
                if kind == "bindings" else \
                state["artifacts"][kind]["status"] == "accepted"

    @allure.title("M16: пропуск фазы блокируется (implementation до review)")
    def test_skip_phase_blocked(self, project):
        orchestrator = project.orchestrator()
        project.prepare_harness()
        project.init(orchestrator)
        orchestrator.accept("context", project.context_envelope())
        orchestrator.accept("scenarios", project.scenarios_envelope())
        with pytest.raises(WorkflowBlockedError):
            orchestrator.accept("implementation", project.impl_envelope())

    @allure.title("M16: accept scenarios до context блокируется")
    def test_scenarios_before_context(self, project):
        orchestrator = project.orchestrator()
        project.init(orchestrator)
        with pytest.raises(WorkflowBlockedError):
            orchestrator.accept("scenarios", project.scenarios_envelope())

    @allure.title("Повторный accept того же scenarios-envelope — no-op")
    def test_accept_idempotent(self, project):
        orchestrator = project.orchestrator()
        project.init(orchestrator)
        orchestrator.accept("context", project.context_envelope())
        envelope = project.scenarios_envelope()
        assert orchestrator.accept("scenarios", envelope) == "accepted"
        assert orchestrator.accept("scenarios", envelope) == "no-op"

    @allure.title("M16: digest review не совпадает с frozen scenarios")
    def test_review_digest_mismatch(self, project):
        orchestrator = project.orchestrator()
        project.init(orchestrator)
        orchestrator.accept("context", project.context_envelope())
        orchestrator.accept("scenarios", project.scenarios_envelope())
        envelope = project.review_envelope(scenarios_sha="0" * 64)
        with pytest.raises(WorkflowBlockedError):
            orchestrator.accept("review", envelope)

    @allure.title("review needs_decision блокирует phase до исправления")
    def test_review_needs_decision(self, project):
        orchestrator = project.orchestrator()
        project.init(orchestrator)
        orchestrator.accept("context", project.context_envelope())
        orchestrator.accept("scenarios", project.scenarios_envelope())
        orchestrator.accept(
            "review", project.review_envelope(decision="needs_decision"))
        state, _ = _load(project)
        assert state["phase_status"] == "blocked"
        with pytest.raises(WorkflowBlockedError):
            orchestrator.accept("implementation", project.impl_envelope())

    @allure.title("Конфликт bindings на той же ревизии — 69, не silent-замена")
    def test_bindings_conflict(self, project):
        orchestrator = project.drive_to_implementation_ready()
        orchestrator.accept("bindings", project.bindings_envelope())
        changed = dict(C.BINDINGS)
        changed[C.SCENARIO_IDS[0]] = 9999
        envelope = project.envelope(
            "bindings", {"mapping": changed, "source": "assign"},
            name="bindings2.json")
        with pytest.raises(WorkflowBlockedError):
            orchestrator.accept("bindings", envelope)

    @allure.title("Envelope без документа/актора/полей отклоняется")
    def test_strict_envelope(self, project):
        orchestrator = project.orchestrator()
        project.init(orchestrator)
        path = project.root / "envelopes" / "bad.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(
            {"envelope_version": 1, "artifact": "context",
             "actor": "alien", "payload": {"sources": []}}),
            encoding="utf-8")
        with pytest.raises(WorkflowValidationError):
            orchestrator.accept("context", path)

    @allure.title("document digest envelope должен совпадать с файлом")
    def test_document_digest(self, project):
        orchestrator = project.orchestrator()
        project.init(orchestrator)
        envelope = project.context_envelope()
        data = json.loads(Path(envelope).read_text())
        data["document"]["sha256"] = "0" * 64
        Path(envelope).write_text(json.dumps(data))
        with pytest.raises(WorkflowValidationError):
            orchestrator.accept("context", envelope)

    @allure.title("Context: digest источника сверяется с app checkout")
    def test_context_source_mismatch(self, project):
        orchestrator = project.orchestrator()
        project.init(orchestrator)
        sources = project.context_sources()
        sources[0]["sha256"] = "0" * 64
        envelope = project.envelope("context", {"sources": sources},
                                    name="context-bad.json")
        with pytest.raises(WorkflowBlockedError):
            orchestrator.accept("context", envelope)

    @allure.title("Scenarios: каждый requirement должен быть покрыт")
    def test_coverage_required(self, project):
        orchestrator = project.orchestrator()
        project.init(orchestrator)
        orchestrator.accept("context", project.context_envelope())
        envelope = project.envelope(
            "scenarios",
            {"scenario_ids": [C.SCENARIO_IDS[0]],
             "requirement_coverage": {"R1": [C.SCENARIO_IDS[0]]}},
            name="scenarios-partial.json")
        with pytest.raises(WorkflowBlockedError):
            orchestrator.accept("scenarios", envelope)

    @allure.title("Implementation: node IDs обязаны покрывать сценарии")
    def test_node_ids_gate(self, project):
        orchestrator = project.orchestrator()
        project.prepare_harness()
        project.init(orchestrator)
        orchestrator.accept("context", project.context_envelope())
        orchestrator.accept("scenarios", project.scenarios_envelope())
        orchestrator.accept("review", project.review_envelope())
        utils.list_ok(project.runner, ["tests/api/x.py::TestX::test_y"])
        with pytest.raises(WorkflowBlockedError):
            orchestrator.accept("implementation", project.impl_envelope())

    @allure.title("Implementation: падение compile блокирует accept")
    def test_compile_failure_blocks(self, project):
        orchestrator = project.orchestrator()
        project.runner.on_tool("tools/compile-tests.sh",
                               utils.ok_lines([], code=1))
        project.init(orchestrator)
        orchestrator.accept("context", project.context_envelope())
        orchestrator.accept("scenarios", project.scenarios_envelope())
        orchestrator.accept("review", project.review_envelope())
        with pytest.raises(WorkflowBlockedError):
            orchestrator.accept("implementation", project.impl_envelope())


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("T8: новые входы инвалидируют downstream")
@allure.severity(allure.severity_level.CRITICAL)
class TestRevisionInvalidation:
    @allure.title("Новый patch: цепочка артефактов уходит в stale")
    def test_new_patch_stales(self, project):
        orchestrator = project.drive_to_implementation_ready()
        project.init(orchestrator, app_head_sha256=C.APP_PATCH_SHA256_2)
        state, _ = _load(project)
        assert state["input"]["revision"] == 2
        for kind in ("context", "scenarios", "review", "implementation"):
            assert state["artifacts"][kind]["status"] == "stale"
        assert state["phase"] == "initialized"

    @allure.title("Новый tests snapshot инвалидирует только implementation")
    def test_new_tests_snapshot(self, project):
        orchestrator = project.drive_to_implementation_ready()
        project.init(orchestrator, tests_commit=C.TESTS_COMMIT_2,
                     tests_dirty=True,
                     tests_snapshot_sha256="9" * 64)
        state, _ = _load(project)
        assert state["artifacts"]["implementation"]["status"] == "stale"
        assert state["artifacts"]["review"]["status"] == "accepted"
        assert state["phase"] == "approved"

    @allure.title("Изменённые требования инвалидируют сценарии и дальше")
    def test_new_requirements(self, project):
        orchestrator = project.drive_to_implementation_ready()
        new_text = C.REQUIREMENTS_TEXT + "| R3 | новое |\n"
        utils.write_doc(project.root, C.REQUIREMENTS_REL, new_text)
        project.init(orchestrator,
                     requirement_ids=C.REQUIREMENT_IDS + ["R3"])
        state, _ = _load(project)
        assert state["artifacts"]["scenarios"]["status"] == "stale"
        assert state["artifacts"]["implementation"]["status"] == "stale"
        assert state["artifacts"]["context"]["status"] == "accepted"

    @allure.title("dirty-источник без snapshot допустим, с git_sha — нет")
    def test_dirty_source_shape(self, project):
        _, outcome = project.init(tests_dirty=True,
                                  tests_snapshot_sha256="8" * 64)
        assert outcome == "created"
        state, _ = _load(project)
        assert state["input"]["revision_data"]["tests_repo"]["dirty"]

    @allure.title("Изменённое execution-окружение инвалидирует прогоны")
    def test_changed_environment_stales_executions(self, project):
        orchestrator = project.drive_to_executed()
        assert project.workflow_state()["phase"] == "executed"
        project.init(orchestrator, strength_evidence={
            "variant": "base", "required": True, "scope": "api",
            "expect": {"total": 5, "failed": 5}})
        state = project.workflow_state()
        assert state["input"]["revision"] == 2
        assert state["phase"] == "implementation_ready"
        assert all(e["bound_revision"] == 1 for e in state["executions"])
