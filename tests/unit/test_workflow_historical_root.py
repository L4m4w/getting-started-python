"""33-P-B регрессии: записанный внешний evidence root для исторического
base-execution.

- ``import_execution --evidence-root`` принимается только вместе с
  accepted ``historical_baseline_acceptance`` provenance для base.
- Location записывается в execution entry (``evidence_root``) и все
  чтения — restart, re-import, rebind — идут по записанному root, а не
  по текущему checkout.
- Любой resolved path evidence обязан оставаться внутри root: relative,
  absolute и symlink эскейпы блокируются.
- Внешнее дерево read-only навсегда: prepare/publish/verify/reconcile
  не вызывают delegated CLI и не создают lock/temp/package/state файлов,
  включая durable статусы ``sent`` и ``uploaded``.
- Наблюдение base-execution никогда не перезаписывает publication
  канала head.

Все проверки строго offline в tmp dirs: fake runner / isolated stores.
"""
import copy
import json
import os
from pathlib import Path
import shutil

import allure
import pytest

from infrastructure.reporting.testops import results as tresults
from infrastructure.reporting.testops import state as tstate
from infrastructure.workflow import adapters
from infrastructure.workflow import state as state_mod
from infrastructure.workflow.state import (
    WorkflowBlockedError, WorkflowValidationError)
from test_data.consts import workflow as C
from test_data.consts import workflow_historical_root as HR
from test_data.utils import workflow as utils


@pytest.fixture
def project(tmp_path):
    return utils.Project(tmp_path / "proj")


def _external_evidence(project, tmp_path):
    """Исторический baseline во внешнем root + accepted provenance record.

    Evidence собирается в project.root с историческим содержимым теста и
    переносится во внешний root, поэтому локальное default-location
    сознательно отсутствует — любое чтение идёт только через записанный
    root.
    """
    test_path = project.root / C.TEST_FILES[0]
    test_path.write_text(C.HISTORICAL_TEST_CONTENT, encoding="utf-8")
    historical_sha = utils.sha256_file(test_path)
    utils.write_manifest(
        project.root, C.EXECUTION_BASE, C.BASE_JUNIT, 1,
        declared={"app_base_sha": C.APP_BASE_SHA},
        tests_commit=C.TESTS_COMMIT_2)
    ext_root = tmp_path / HR.EXTERNAL_ROOT_NAME
    evidence = utils.move_evidence(
        project.root, ext_root, C.EXECUTION_BASE)
    test_path.write_text(C.TEST_FILE_CONTENT, encoding="utf-8")
    current_sha = utils.sha256_file(test_path)
    review_doc = utils.write_doc(
        project.root, C.REVIEW_WAVE_REL, C.REVIEW_WAVE_TEXT)
    project.sync_tests_commit(C.TESTS_COMMIT)
    record = utils.historical_acceptance(
        evidence, review_doc=review_doc,
        historical_sha=historical_sha, current_sha=current_sha)
    return ext_root, evidence, record


def _orchestrator(project, record):
    orch = project.orchestrator(accepted_provenance=(record,))
    project.drive_to_implementation_ready(orch)
    return orch


def _edit_manifest(evidence, mutate):
    path = Path(evidence) / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mutate(manifest)
    path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def _entry(project, execution_id=C.EXECUTION_BASE):
    return next(item for item in project.workflow_state()["executions"]
                if item["execution_id"] == execution_id)


def _is_within(path, root):
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return False
    return True


class _ReadSpy:
    """Шпион чтений evidence: фиксирует первый (path) аргумент каждого
    публичного helper'а чтения. Доказывает, что отказ произошёл ДО
    чтения содержимого посторонних файлов, а не по digest позже."""

    _READS = (
        (adapters, ("read_manifest", "junit_summary")),
        (tresults, ("load_results", "results_digest", "scan_assignments",
                    "validate_attachments", "verify_source_digest",
                    "verify_package")),
        (tstate, ("load_state",)),
        (state_mod, ("sha256_file",)),
    )

    def __init__(self, monkeypatch):
        self.calls = []
        spy = self

        def wrap(module, name):
            original = getattr(module, name)

            def proxy(first, *args, **kwargs):
                spy.calls.append((name, first))
                return original(first, *args, **kwargs)

            monkeypatch.setattr(module, name, proxy)

        for module, names in self._READS:
            for name in names:
                wrap(module, name)

    def assert_no_foreign_reads(self, *roots):
        """Каждое выполненное чтение осталось внутри разрешённых root."""
        for name, first in self.calls:
            if not any(_is_within(first, root) for root in roots):
                pytest.fail(
                    f"foreign read through {name}: {first!r} resolves "
                    f"outside {[str(root) for root in roots]}")


def _member_defect(defect, evidence, ext_root, outside):
    """Внедрить member-level дефект во внешнее evidence дерево."""
    foreign = outside / HR.FOREIGN_PAYLOAD_NAME
    if defect in ("allure_result_symlink", "allure_container_symlink",
                  "allure_attachment_symlink", "source_member_symlink"):
        foreign.write_text("{}", encoding="utf-8")
        member = {
            "allure_result_symlink": (
                evidence / "allure-results" / HR.ESCAPE_RESULT_NAME),
            "allure_container_symlink": (
                evidence / "allure-results" / HR.ESCAPE_CONTAINER_NAME),
            "allure_attachment_symlink": (
                evidence / "allure-results" / HR.ESCAPE_ATTACHMENT_NAME),
            "source_member_symlink": (
                evidence / "sources" / HR.ESCAPE_MEMBER_NAME),
        }[defect]
        os.symlink(foreign, member)
        return
    if defect == "testops_member_symlink":
        foreign.write_text("{}", encoding="utf-8")
        state_dir = utils.make_testops_state(
            ext_root, C.EXECUTION_BASE, upload_status="pending",
            with_package=False,
            results_dir=evidence / "allure-results")
        os.symlink(foreign, Path(state_dir) / HR.ESCAPE_MEMBER_NAME)
        return
    if defect == "default_allure_dir_symlink":
        (outside / "x-result.json").write_text("{}", encoding="utf-8")
        _edit_manifest(
            evidence,
            lambda m: m["artifacts"].pop("allure_results", None))
        shutil.rmtree(evidence / "allure-results")
        os.symlink(outside, evidence / "allure-results")
        return
    if defect == "broken_member_symlink":
        os.symlink(ext_root / "no-such-target",
                   evidence / "allure-results" / HR.ESCAPE_MEMBER_NAME)
        return
    if defect == "dir_cycle_symlink":
        os.symlink(evidence / "allure-results",
                   evidence / "allure-results" / HR.CYCLE_DIR_NAME)
        return
    if defect == "package_member_symlink":
        foreign.write_text("{}", encoding="utf-8")
        state_dir = Path(utils.make_testops_state(
            ext_root, C.EXECUTION_BASE, upload_status="uploaded",
            results_dir=evidence / "allure-results"))
        package = ext_root / HR.DETACHED_PACKAGE_NAME
        package.mkdir()
        (package / "one-result.json").write_text("{}", encoding="utf-8")
        os.symlink(foreign, package / HR.ESCAPE_MEMBER_NAME)
        state_path = state_dir / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["package"]["dir"] = str(package)
        state_path.write_text(
            json.dumps(state, indent=2) + "\n", encoding="utf-8")
        return
    if defect == "results_path_escape":
        state_dir = Path(utils.make_testops_state(
            ext_root, C.EXECUTION_BASE, upload_status="uploaded",
            results_dir=evidence / "allure-results"))
        state_path = state_dir / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["results"]["path"] = str(outside)
        state_path.write_text(
            json.dumps(state, indent=2) + "\n", encoding="utf-8")
        return
    raise AssertionError(f"unknown member defect {defect}")


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("33B: записанный внешний evidence root исторического base")
@allure.severity(allure.severity_level.BLOCKER)
class TestHistoricalEvidenceRoot:
    @allure.title("Принятый исторический baseline с --evidence-root "
                  "записывает external location в execution entry")
    def test_external_root_import_records_location(self, project, tmp_path):
        with allure.step("Собрать внешний baseline и provenance record"):
            ext_root, evidence, record = _external_evidence(
                project, tmp_path)
            orch = _orchestrator(project, record)
        with allure.step("Импорт с evidence_root фиксирует location"):
            outcome = orch.import_execution(
                C.EXECUTION_BASE, provenance=record,
                evidence_root=str(ext_root))
            assert outcome["outcome"] == "imported"
            assert outcome["variant"] == "base"
            assert outcome["bound_revision"] == 1
        with allure.step("Entry хранит записанный root и derived dirs"):
            entry = _entry(project)
            assert entry["evidence_root"] == str(ext_root.resolve())
            assert entry["evidence_dir"] == str(evidence.resolve())
            assert entry["testops_state_dir"] == str(
                (ext_root / "artifacts" / "testops"
                 / C.EXECUTION_BASE).resolve())
            assert entry["provenance"] == record
            assert not (project.root / "artifacts" / "harness"
                        / C.EXECUTION_BASE).exists()

    @allure.title("--evidence-root без --provenance отклоняется до чтения "
                  "evidence")
    def test_evidence_root_requires_provenance(self, project, tmp_path):
        with allure.step("Внешний root без provenance"):
            ext_root = tmp_path / HR.EXTERNAL_ROOT_NAME
            ext_root.mkdir()
            orch = project.drive_to_implementation_ready()
        with allure.step("Import отклонён как validation error"):
            with pytest.raises(WorkflowValidationError,
                               match="requires --provenance"):
                orch.import_execution(
                    C.EXECUTION_BASE, evidence_root=str(ext_root))
            assert not _entry_exists(project)

    @allure.title("Конфликт root или provenance решается до no-op")
    def test_conflicts_blocked_before_noop(self, project, tmp_path):
        with allure.step("Записанный внешний baseline"):
            ext_root, evidence, record = _external_evidence(
                project, tmp_path)
            orch = _orchestrator(project, record)
            assert orch.import_execution(
                C.EXECUTION_BASE, provenance=record,
                evidence_root=str(ext_root))["outcome"] == "imported"
        with allure.step("Re-import с другим root — blocked, не no-op"):
            other_root = tmp_path / HR.CONFLICT_ROOT_NAME
            other_root.mkdir()
            outcome = orch.import_execution(
                C.EXECUTION_BASE, provenance=record,
                evidence_root=str(other_root))
            assert outcome["outcome"] == "blocked"
            assert outcome["exit"] == 69
            assert "contradicts the recorded location" in outcome["detail"]
        with allure.step("Re-import с другой provenance — blocked"):
            forged = copy.deepcopy(record)
            forged["junit_sha256"] = HR.FORGED_JUNIT_SHA256
            outcome = orch.import_execution(
                C.EXECUTION_BASE, provenance=forged)
            assert outcome["outcome"] == "blocked"
            assert outcome["exit"] == 69
            assert "contradicts the recorded acceptance" in outcome["detail"]
        with allure.step("Идентичный ввод остаётся честным no-op"):
            outcome = orch.import_execution(
                C.EXECUTION_BASE, provenance=record,
                evidence_root=str(ext_root))
            assert outcome["outcome"] == "no-op"

    @allure.title("Relative, несуществующий и store-пересекающийся "
                  "evidence root отклоняются")
    @pytest.mark.parametrize("bad", ("relative", "missing", "store_parent"))
    def test_evidence_root_validation(self, project, tmp_path, bad):
        with allure.step(f"Невалидный root: {bad}"):
            orch = project.drive_to_implementation_ready()
            if bad == "relative":
                candidate = HR.RELATIVE_ROOT
            elif bad == "missing":
                candidate = str(tmp_path / "no-such-root")
            else:
                candidate = str(tmp_path)
        with allure.step("WorkflowValidationError до любого чтения"):
            with pytest.raises(WorkflowValidationError):
                orch.import_execution(
                    C.EXECUTION_BASE, provenance={"schema_version": "x"},
                    evidence_root=candidate)

    @allure.title("Absolute artifact path, traversal и symlink-эскейпы "
                  "блокируются при импорте")
    @pytest.mark.parametrize("defect", (
        "absolute_junit", "traversal_junit", "symlink_allure",
        "symlink_state", "absolute_source_copy",
    ))
    def test_external_containment_rejects_escapes(
            self, project, tmp_path, defect):
        with allure.step("Внешний baseline с дефектом путей"):
            ext_root, evidence, record = _external_evidence(
                project, tmp_path)
            orch = _orchestrator(project, record)
            outside = tmp_path / HR.ESCAPE_TARGET_NAME
            if defect == "absolute_junit":
                _edit_manifest(
                    evidence,
                    lambda m: m["artifacts"].__setitem__(
                        "junit", HR.ABSOLUTE_ARTIFACT))
            elif defect == "traversal_junit":
                _edit_manifest(
                    evidence,
                    lambda m: m["artifacts"].__setitem__(
                        "junit", HR.TRAVERSAL_ARTIFACT))
            elif defect == "symlink_allure":
                outside.mkdir()
                (outside / "x-result.json").write_text(
                    "{}", encoding="utf-8")
                shutil.rmtree(evidence / "allure-results")
                os.symlink(outside, evidence / "allure-results")
            elif defect == "symlink_state":
                outside.mkdir()
                payload = outside / "state.json"
                payload.write_text("{}", encoding="utf-8")
                state_dir = (ext_root / "artifacts" / "testops"
                             / C.EXECUTION_BASE)
                state_dir.mkdir(parents=True)
                os.symlink(payload, state_dir / "state.json")
            else:
                _edit_manifest(
                    evidence,
                    lambda m: m["source_identity"]["copies"].append(
                        HR.ABSOLUTE_SOURCE_COPY))
        with allure.step("Import блокируется на containment"):
            outcome = orch.import_execution(
                C.EXECUTION_BASE, provenance=record,
                evidence_root=str(ext_root))
            assert outcome["outcome"] == "blocked"
            assert outcome["exit"] == 69
            assert ("escapes the evidence root" in outcome["detail"]
                    or "must be evidence-relative" in outcome["detail"]
                    or "must be relative" in outcome["detail"])
            assert not _entry_exists(project)

    @allure.title("Restart и re-import читают записанный root; rebind "
                  "после ревизии идёт во внешнее дерево")
    def test_recorded_root_survives_restart_and_rebind(
            self, project, tmp_path):
        with allure.step("Записанный внешний baseline"):
            ext_root, evidence, record = _external_evidence(
                project, tmp_path)
            orch = _orchestrator(project, record)
            assert orch.import_execution(
                C.EXECUTION_BASE, provenance=record,
                evidence_root=str(ext_root))["outcome"] == "imported"
        with allure.step("Restart: новый Orchestrator, reimport — no-op"):
            orch2 = project.orchestrator(accepted_provenance=(record,))
            outcome = orch2.import_execution(
                C.EXECUTION_BASE, provenance=record,
                evidence_root=str(ext_root))
            assert outcome["outcome"] == "no-op"
        with allure.step("Bump revision до implementation_ready + head run"):
            project.init(orch2, app_head_sha256=C.APP_PATCH_SHA256_2)
            assert project.workflow_state()["input"]["revision"] == 2
            for kind, make in (("context", project.context_envelope),
                               ("scenarios", project.scenarios_envelope),
                               ("review", project.review_envelope),
                               ("implementation", project.impl_envelope),
                               ("bindings", project.bindings_envelope)):
                orch2.accept(kind, make())
            utils.harness_run(
                project.runner, project.root, HR.EXECUTION_HEAD_R2,
                C.HEAD_JUNIT, 0,
                declared={"app_base_sha": C.APP_BASE_SHA,
                          "app_patch_sha256": C.APP_PATCH_SHA256_2})
            assert orch2.run_execution("head")["outcome"] == "recorded"
        with allure.step("Decoy-манифест в локальном default-location"):
            utils.write_manifest(
                project.root, C.EXECUTION_BASE, C.BASE_JUNIT, 1,
                declared={"app_base_sha": C.APP_BASE_SHA},
                tests_commit=C.TESTS_COMMIT_2, status="failed")
        with allure.step("Rebind читает записанный внешний root"):
            rebind = orch2.import_execution(C.EXECUTION_BASE)
            assert rebind["outcome"] == "rebound"
            assert rebind["bound_revision"] == 2
            entry = _entry(project)
            assert entry["bound_revision"] == 2
            assert entry["rebound_from_revision"] == 1
            assert entry["evidence_root"] == str(ext_root.resolve())
            assert entry["evidence_dir"] == str(evidence.resolve())

    @allure.title("Внешнее evidence read-only в статусах sent/uploaded: "
                  "ноль delegated вызовов и записей")
    @pytest.mark.parametrize("upload_status", ("sent", "uploaded"))
    def test_external_evidence_stays_read_only(
            self, project, tmp_path, upload_status):
        with allure.step(f"Внешний baseline с TestOps state "
                         f"{upload_status}"):
            ext_root, evidence, record = _external_evidence(
                project, tmp_path)
            utils.make_testops_state(
                ext_root, C.EXECUTION_BASE, upload_status=upload_status,
                results_dir=evidence / "allure-results")
            orch = _orchestrator(project, record)
            before = utils.snapshot_tree_metadata(
                ext_root, include_artifacts=True)
            calls_before = len(project.runner.calls)
        with allure.step("Импорт без единой записи во внешний root"):
            outcome = orch.import_execution(
                C.EXECUTION_BASE, provenance=record,
                evidence_root=str(ext_root))
            assert outcome["outcome"] == "imported"
            assert utils.snapshot_tree_metadata(
                ext_root, include_artifacts=True) == before
        with allure.step("prepare/publish/verify/reconcile не dispatch'ят"):
            with pytest.raises(WorkflowBlockedError):
                orch.prepare_testops(C.EXECUTION_BASE)
            with pytest.raises(WorkflowBlockedError):
                orch.publish_testops(C.EXECUTION_BASE, execute=True)
            with pytest.raises(WorkflowBlockedError):
                orch.verify_testops(C.EXECUTION_BASE, online=True)
            orch.reconcile()
        with allure.step("Runner не вызван, дерево байт-в-байт прежнее"):
            assert project.runner.tool_calls("tools/run-testops.sh") == []
            assert len(project.runner.calls) == calls_before
            assert utils.snapshot_tree_metadata(
                ext_root, include_artifacts=True) == before

    @allure.title("Наблюдение base-execution никогда не перезаписывает "
                  "publication канала head")
    def test_base_observation_never_mutates_head_publication(
            self, project, tmp_path):
        with allure.step("Head execution с локальным TestOps state sent"):
            ext_root, evidence, record = _external_evidence(
                project, tmp_path)
            utils.make_testops_state(
                ext_root, C.EXECUTION_BASE, upload_status="uploaded",
                results_dir=evidence / "allure-results")
            orch = _orchestrator(project, record)
            orch.accept("bindings", project.bindings_envelope())
            utils.harness_run(
                project.runner, project.root, C.EXECUTION_HEAD,
                C.HEAD_JUNIT, 0,
                declared={"app_base_sha": C.APP_BASE_SHA,
                          "app_patch_sha256": C.APP_PATCH_SHA256})
            orch.run_execution("head")
            utils.make_testops_state(
                project.root, C.EXECUTION_HEAD, upload_status="sent")
        with allure.step("Head observation заполняет publication канал"):
            adapter = adapters.TestOpsAdapter(project.root, project.runner)
            state = project.workflow_state()
            orch._observe_testops(
                state, adapter, C.EXECUTION_HEAD, variant="head")
            pubs = state["publications"]["testops"]
            assert pubs["execution_id"] == C.EXECUTION_HEAD
            workflow_dir = next(
                p for p in project.store_dir.iterdir()
                if p.is_dir()
                and state_mod.WORKFLOW_ID_RE.fullmatch(p.name))
            state_mod.save_state(workflow_dir, state)
            head_pubs = copy.deepcopy(pubs)
        with allure.step("Base import/observation не трогают канал head"):
            outcome = orch.import_execution(
                C.EXECUTION_BASE, provenance=record,
                evidence_root=str(ext_root))
            assert outcome["outcome"] == "imported"
            orch._observe_testops(
                state, adapter, C.EXECUTION_BASE, variant="base")
            assert state["publications"]["testops"] == head_pubs
            stored = project.workflow_state()["publications"]["testops"]
            assert stored == head_pubs
            base_sha = utils.testops_state_sha(ext_root, C.EXECUTION_BASE)
            assert (stored["last_observation"]["state_sha256"]
                    != base_sha)

    @allure.title("Symlink-манифест за пределами root блокируется до "
                  "первого чтения (spy: ноль вызовов чтения)")
    def test_manifest_symlink_blocked_before_any_read(
            self, project, tmp_path, monkeypatch):
        with allure.step("manifest.json — symlink на внешний файл"):
            ext_root, evidence, record = _external_evidence(
                project, tmp_path)
            orch = _orchestrator(project, record)
            outside = tmp_path / HR.ESCAPE_TARGET_NAME
            outside.mkdir()
            foreign = outside / HR.FOREIGN_MANIFEST_NAME
            foreign.write_text('{"schema_version": 2}', encoding="utf-8")
            (evidence / "manifest.json").unlink()
            os.symlink(foreign, evidence / "manifest.json")
            spy = _ReadSpy(monkeypatch)
        with allure.step("Import отклонён до вызова read_manifest"):
            outcome = orch.import_execution(
                C.EXECUTION_BASE, provenance=record,
                evidence_root=str(ext_root))
            assert outcome["outcome"] == "blocked"
            assert outcome["exit"] == 69
            assert "escapes the evidence root" in outcome["detail"]
        with allure.step("Ни одного чтения evidence вообще"):
            assert spy.calls == []
            assert not _entry_exists(project)

    @allure.title("Member-эскейпы, дефолтные пути и дефекты ссылок "
                  "блокируются до чтения содержимого (spy)")
    @pytest.mark.parametrize("defect", (
        "allure_result_symlink", "allure_container_symlink",
        "allure_attachment_symlink", "source_member_symlink",
        "testops_member_symlink", "default_allure_dir_symlink",
        "broken_member_symlink", "dir_cycle_symlink",
        "package_member_symlink", "results_path_escape",
    ))
    def test_member_escapes_blocked_before_content_reads(
            self, project, tmp_path, monkeypatch, defect):
        with allure.step(f"Внешний baseline с дефектом {defect}"):
            ext_root, evidence, record = _external_evidence(
                project, tmp_path)
            orch = _orchestrator(project, record)
            outside = tmp_path / HR.ESCAPE_TARGET_NAME
            outside.mkdir()
            _member_defect(defect, evidence, ext_root, outside)
            spy = _ReadSpy(monkeypatch)
        with allure.step("Import отклонён до чтения member content"):
            if defect in ("package_member_symlink",
                          "results_path_escape"):
                with pytest.raises(WorkflowBlockedError):
                    orch.import_execution(
                        C.EXECUTION_BASE, provenance=record,
                        evidence_root=str(ext_root))
            else:
                outcome = orch.import_execution(
                    C.EXECUTION_BASE, provenance=record,
                    evidence_root=str(ext_root))
                assert outcome["outcome"] == "blocked"
                assert outcome["exit"] == 69
        with allure.step("Ни одного чтения за пределами root"):
            spy.assert_no_foreign_reads(ext_root, project.root)
            assert not _entry_exists(project)

    @allure.title("Recorded root ревалидируется при последующих чтениях: "
                  "removed/symlinked/escaping-dir — controlled block")
    @pytest.mark.parametrize("tamper", (
        "root_removed", "root_symlinked", "artifacts_symlinked"))
    def test_recorded_root_revalidated_on_later_reads(
            self, project, tmp_path, monkeypatch, tamper):
        with allure.step("Записанный внешний baseline"):
            ext_root, evidence, record = _external_evidence(
                project, tmp_path)
            orch = _orchestrator(project, record)
            assert orch.import_execution(
                C.EXECUTION_BASE, provenance=record,
                evidence_root=str(ext_root))["outcome"] == "imported"
        with allure.step(f"Испортить recorded root: {tamper}"):
            moved = tmp_path / HR.MOVED_ROOT_NAME
            outside = tmp_path / HR.ESCAPE_TARGET_NAME
            if tamper == "root_removed":
                ext_root.rename(moved)
            elif tamper == "root_symlinked":
                ext_root.rename(moved)
                os.symlink(moved, ext_root)
            else:
                outside.mkdir()
                (ext_root / "artifacts").rename(outside / "artifacts")
                os.symlink(outside / "artifacts",
                           ext_root / "artifacts")
            spy = _ReadSpy(monkeypatch)
        with allure.step("Последующие чтения — controlled block, "
                         "без foreign read"):
            adapter = adapters.TestOpsAdapter(project.root, project.runner)
            state = project.workflow_state()
            entry = _entry(project)
            with pytest.raises(WorkflowBlockedError):
                orch._recorded_execution_dirs(entry)
            with pytest.raises(WorkflowBlockedError):
                orch._observe_testops(
                    state, adapter, C.EXECUTION_BASE, variant="base")
            assert spy.calls == []

    @allure.title("Upload intent по внешнему execution: blocked без "
                  "adopt/retryable, чтений, записей и delegated calls")
    @pytest.mark.parametrize("upload_status", ("sent", "uploaded"))
    def test_reconcile_upload_intent_external_blocked(
            self, project, tmp_path, monkeypatch, upload_status):
        with allure.step(f"Внешний baseline с TestOps {upload_status} "
                         "и upload intent"):
            ext_root, evidence, record = _external_evidence(
                project, tmp_path)
            utils.make_testops_state(
                ext_root, C.EXECUTION_BASE, upload_status=upload_status,
                results_dir=evidence / "allure-results")
            orch = _orchestrator(project, record)
            assert orch.import_execution(
                C.EXECUTION_BASE, provenance=record,
                evidence_root=str(ext_root))["outcome"] == "imported"
            state = project.workflow_state()
            adapter = adapters.TestOpsAdapter(
                project.root, project.runner)
            intent = state_mod.new_intent(
                state, "testops.upload",
                {"execution": C.EXECUTION_BASE})
            spy = _ReadSpy(monkeypatch)
            snapshot = utils.snapshot_tree_metadata(
                ext_root, include_artifacts=True)
            calls_before = len(project.runner.calls)
        with allure.step("Resolver возвращает blocked; intent не меняется"):
            result = orch._reconcile_upload(state, adapter, intent)
            assert result["action"] == "blocked"
            assert intent["status"] == "declared"
        with allure.step("Ни delegated calls, ни чтений, ни записей"):
            assert spy.calls == []
            assert len(project.runner.calls) == calls_before
            assert utils.snapshot_tree_metadata(
                ext_root, include_artifacts=True) == snapshot

    @allure.title("snapshot_tree_metadata фиксирует dirs, mode, mtime_ns "
                  "и текст symlink для no-write контроля")
    def test_snapshot_tree_metadata_covers_metadata_and_dirs(
            self, tmp_path):
        with allure.step("Дерево с пустым каталогом, файлом и symlink"):
            root = tmp_path / "snap-root"
            (root / "empty-dir").mkdir(parents=True)
            data_dir = root / "data"
            data_dir.mkdir()
            target = data_dir / "target.txt"
            target.write_text("alpha", encoding="utf-8")
            link = data_dir / "link"
            os.symlink(target, link)
            snap = utils.snapshot_tree_metadata(
                root, include_artifacts=True)
        with allure.step("Записи содержат тип, режим и содержимое"):
            assert snap["empty-dir"]["type"] == "dir"
            assert snap["data"]["type"] == "dir"
            file_rec = snap["data/target.txt"]
            assert file_rec["type"] == "file"
            assert file_rec["sha256"] == utils.sha256_file(target)
            assert file_rec["size"] == target.stat().st_size
            assert isinstance(file_rec["mtime_ns"], int)
            assert isinstance(file_rec["mode"], int)
            assert snap["data/link"]["type"] == "symlink"
            assert snap["data/link"]["target"] == os.readlink(link)
        with allure.step("Байты цели ссылкой не захватываются"):
            target.write_text("beta", encoding="utf-8")
            changed = utils.snapshot_tree_metadata(
                root, include_artifacts=True)
            assert changed["data/link"] == snap["data/link"]
            assert (changed["data/target.txt"]["sha256"]
                    != snap["data/target.txt"]["sha256"])
        with allure.step("Пустой lock-каталог и смена режима видны"):
            (root / "execution.lock-gate").mkdir()
            locked = utils.snapshot_tree_metadata(
                root, include_artifacts=True)
            assert locked["execution.lock-gate"]["type"] == "dir"
            assert locked != changed
            os.chmod(target, 0o600)
            chmoded = utils.snapshot_tree_metadata(
                root, include_artifacts=True)
            assert (chmoded["data/target.txt"]["mode"]
                    != locked["data/target.txt"]["mode"])


    @allure.title("Malformed manifest containers give controlled block")
    @pytest.mark.parametrize("field_path, value", HR.MALFORMED_MANIFEST_CONTAINERS)
    def test_manifest_container_shape_refused(self, project, tmp_path, field_path, value):
        with allure.step("Подготовить baseline и испортить форму container"):
            ext_root, evidence, record = _external_evidence(project, tmp_path)
            orch = _orchestrator(project, record)
            def mutate(manifest):
                parent = manifest
                for key in field_path[:-1]:
                    parent = parent.setdefault(key, {})
                parent[field_path[-1]] = copy.deepcopy(value)
            _edit_manifest(evidence, mutate)
        with allure.step("Отклонить malformed manifest без AttributeError"):
            outcome = orch.import_execution(C.EXECUTION_BASE, provenance=record,
                                            evidence_root=str(ext_root))
            assert outcome["outcome"] == "blocked" and outcome["exit"] == 69
            assert "manifest" in outcome["detail"]
            assert not _entry_exists(project)
        with allure.step("Проверить также прямой before-read shape guard"):
            manifest = json.loads((evidence / "manifest.json").read_text())
            assert adapters.manifest_shape_problems(manifest)
            assert orch._external_containment_problems(
                manifest, evidence, ext_root / "artifacts" / "testops" / C.EXECUTION_BASE,
                ext_root)

    @allure.title("FIFO result is refused before result readers")
    def test_non_regular_result_refused_before_read(self, project, tmp_path, monkeypatch):
        with allure.step("Добавить FIFO в temp evidence без writer"):
            ext_root, evidence, record = _external_evidence(project, tmp_path)
            orch = _orchestrator(project, record)
            os.mkfifo(evidence / "allure-results" / HR.NON_REGULAR_RESULT_NAME)
            def forbidden(*args, **kwargs):
                pytest.fail("non-regular member reached content reader")
            monkeypatch.setattr(tresults, "load_results", forbidden)
            monkeypatch.setattr(tresults, "results_digest", forbidden)
            monkeypatch.setattr(tresults, "scan_assignments", forbidden)
        with allure.step("Containment отказывает без открытия FIFO"):
            outcome = orch.import_execution(C.EXECUTION_BASE, provenance=record,
                                            evidence_root=str(ext_root))
            assert outcome["outcome"] == "blocked" and outcome["exit"] == 69
            assert "non-regular" in outcome["detail"]
            assert not _entry_exists(project)

    @allure.title("Project-nested historical root is refused, including persisted location")
    def test_project_nested_root_refused(self, project):
        with allure.step("Создать temp historical root под local project"):
            root = project.root / HR.NESTED_ROOT_NAME
            root.mkdir()
            orch = project.drive_to_implementation_ready()
        with allure.step("Caller и recorded location не могут пересечь write area"):
            with pytest.raises(WorkflowValidationError):
                orch._resolve_evidence_root(root)
            harness, testops_dir = orch._execution_dirs(C.EXECUTION_BASE, root=root)
            entry = {"execution_id": C.EXECUTION_BASE, "evidence_root": str(root),
                     "evidence_dir": str(harness), "testops_state_dir": str(testops_dir)}
            with pytest.raises(WorkflowBlockedError):
                orch._validate_persisted_root(entry)



def _entry_exists(project):
    return any(item["execution_id"] == C.EXECUTION_BASE
               for item in project.workflow_state()["executions"])
