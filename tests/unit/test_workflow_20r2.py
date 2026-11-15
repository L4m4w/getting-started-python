"""20R2-регрессии: точный source/scenario contract (R1), разделение patch
digest и immutable Git commit head (R2), проверяемая историческая baseline
provenance без универсального waiver (R3) и durable checkpoints TestOps
plan/assign/package (R4). Все проверки строго offline в temp dirs."""
import copy
import json
from pathlib import Path
import subprocess
import sys

import allure
import pytest

from infrastructure.reporting.testops import results as tresults
from infrastructure.reporting.testops import state as tstate
from infrastructure.workflow import adapters, contracts, state as state_mod
from infrastructure.workflow.orchestrator import Orchestrator
from infrastructure.workflow.state import (
    WorkflowBlockedError, WorkflowSchemaError)
from test_data.consts import category_update as cat_consts
from test_data.consts import workflow as C
from test_data.utils import workflow as utils
from tools import harness as harness_mod


@pytest.fixture
def project(tmp_path):
    return utils.Project(tmp_path / "proj")


def _tool_actions(runner):
    out = []
    for argv in runner.tool_calls("tools/run-testops.sh"):
        for action in ("plan", "assign", "package", "upload", "verify"):
            if action in argv:
                out.append(action)
                break
    return out


def _make_baseline_acceptance(project, evidence_dir, *, review_doc,
                              historical_sha, current_sha):
    manifest_sha = utils.sha256_file(evidence_dir / "manifest.json")
    junit_sha = utils.sha256_file(evidence_dir / "junit.xml")
    allure_sha = tresults.results_digest(evidence_dir / "allure-results")
    return {
        "schema_version": contracts.HISTORICAL_PROVENANCE_SCHEMA_VERSION,
        "kind": contracts.HISTORICAL_PROVENANCE_KIND,
        "pilot_id": C.PILOT_ID,
        "execution_id": evidence_dir.name,
        "variant": "base",
        "app_base_sha": C.APP_BASE_SHA,
        "manifest_sha256": manifest_sha,
        "junit_sha256": junit_sha,
        "allure_results_sha256": allure_sha,
        "contract_version": harness_mod.API_CONTRACT_VERSION,
        "tests_repo": {"commit": C.TESTS_COMMIT_2, "dirty": False},
        "review_decisions": [review_doc],
        "equivalence_scope": {
            "allowed_changed_files": {
                C.TEST_FILES[0]: {
                    "historical_sha256": historical_sha,
                    "current_sha256": current_sha,
                    "reason": "runtime ALLURE_ID markup added after baseline",
                },
            },
        },
    }


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("R1: полный versioned source и scenario contract")
@allure.severity(allure.severity_level.BLOCKER)
class TestR1SourceAndScenarioContract:
    @allure.title("Неполный source scope и три повтора одного сценария без "
                  "Allure блокируются")
    def test_incomplete_sources_and_duplicate_scenarios_blocked(self, project):
        with allure.step("Довести проект до implementation_ready"):
            orchestrator = project.drive_to_implementation_ready()
        with allure.step("Создать manifest с одним документом, тремя "
                         "повторами UNIT-VAL-001 и пустым allure-results"):
            utils.write_manifest(
                project.root, C.EXECUTION_HEAD, C.HEAD_JUNIT, 0,
                declared={"app_base_sha": C.APP_BASE_SHA,
                          "app_patch_sha256": C.APP_PATCH_SHA256},
                names=[C.SCENARIO_IDS[0]] * 3,
                source_files=[C.REQUIREMENTS_REL])
            head = orchestrator.import_execution(C.EXECUTION_HEAD)
        with allure.step("Импортировать корректный базовый прогон"):
            utils.write_manifest(
                project.root, C.EXECUTION_BASE, C.BASE_JUNIT, 1,
                declared={"app_base_sha": C.APP_BASE_SHA})
            base = orchestrator.import_execution(C.EXECUTION_BASE)
        with allure.step("Проверить блокировку head и фазу != executed"):
            assert head["outcome"] == "blocked"
            assert base["outcome"] == "imported"
            assert project.workflow_state()["phase"] == "implementation_ready"

    @allure.title("Отсутствие rechecked_at, неверная contract_version или "
                  "посторонний файл в source_identity блокируются")
    @pytest.mark.parametrize("mutation", (
        "wrong_version", "missing_recheck", "changed_null",
        "duplicate_file", "foreign_file", "unrecorded_copy",
    ))
    def test_source_identity_contract_invariants(self, project, mutation):
        with allure.step("Подготовить валидный head manifest"):
            orchestrator = project.drive_to_implementation_ready()
            evidence = utils.write_manifest(
                project.root, C.EXECUTION_HEAD, C.HEAD_JUNIT, 0,
                declared={"app_base_sha": C.APP_BASE_SHA,
                          "app_patch_sha256": C.APP_PATCH_SHA256})
            manifest_path = evidence / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        with allure.step(f"Внести нарушение контракта: {mutation}"):
            if mutation == "wrong_version":
                manifest["source_identity"]["contract_version"] = "v0-fake"
            elif mutation == "missing_recheck":
                manifest["source_identity"]["rechecked_at"] = None
            elif mutation == "changed_null":
                manifest["source_identity"]["changed_during_run"] = None
            elif mutation == "duplicate_file":
                manifest["source_identity"]["files"].append(
                    dict(manifest["source_identity"]["files"][0]))
            elif mutation == "foreign_file":
                extra = "docs/foreign.py"
                utils.write_doc(project.root, extra, "# foreign\n")
                dest = evidence / "sources" / extra
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text("# foreign\n", encoding="utf-8")
                manifest["source_identity"]["files"].append(
                    {"path": extra, "sha256": utils.sha256_file(dest)})
                manifest["source_identity"]["copies"].append(extra)
            elif mutation == "unrecorded_copy":
                rogue = evidence / "sources" / "rogue.py"
                rogue.write_text("# unrecorded\n", encoding="utf-8")
            manifest_path.write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        with allure.step("Проверить отказ импорта"):
            outcome = orchestrator.import_execution(C.EXECUTION_HEAD)
            assert outcome["outcome"] == "blocked"
            assert project.workflow_state()["phase"] == "implementation_ready"

    @allure.title("Отсутствие Allure, дубликат UUID/сценария, lookalike ID, "
                  "несовпадение статусов и ложные bindings блокируются")
    @pytest.mark.parametrize("defect", (
        "empty_allure", "duplicate_uuid", "duplicate_scenario",
        "lookalike_junit_id", "status_mismatch", "false_binding_label",
        "missing_head_binding_label", "multiple_binding_labels",
    ))
    def test_allure_and_junit_defects_blocked(self, project, defect):
        with allure.step("Подготовить проект с принятыми bindings"):
            orchestrator = project.drive_to_implementation_ready()
            orchestrator.accept("bindings", project.bindings_envelope())
            evidence = utils.write_manifest(
                project.root, C.EXECUTION_HEAD, C.HEAD_JUNIT, 0,
                declared={"app_base_sha": C.APP_BASE_SHA,
                          "app_patch_sha256": C.APP_PATCH_SHA256})
            allure_dir = evidence / "allure-results"
            result_files = sorted(allure_dir.glob("*-result.json"))
        with allure.step(f"Смоделировать дефект результатов: {defect}"):
            if defect == "empty_allure":
                for item in result_files:
                    item.unlink()
            elif defect == "duplicate_uuid":
                first = json.loads(result_files[0].read_text(encoding="utf-8"))
                second = json.loads(result_files[1].read_text(encoding="utf-8"))
                second["uuid"] = first["uuid"]
                result_files[1].write_text(
                    json.dumps(second, ensure_ascii=False), encoding="utf-8")
            elif defect == "duplicate_scenario":
                first = json.loads(result_files[0].read_text(encoding="utf-8"))
                second = json.loads(result_files[1].read_text(encoding="utf-8"))
                second["fullName"] = first["fullName"]
                second["parameters"] = first["parameters"]
                result_files[1].write_text(
                    json.dumps(second, ensure_ascii=False), encoding="utf-8")
            elif defect == "lookalike_junit_id":
                utils.junit_xml(
                    evidence / "junit.xml", C.HEAD_JUNIT,
                    names=[f"test_rejects_invalid[{C.LOOKALIKE_SCENARIO_ID}]",
                           f"test_rejects_invalid[{C.SCENARIO_IDS[1]}]",
                           f"test_accepts_boundary[{C.SCENARIO_IDS[2]}]"])
            elif defect == "status_mismatch":
                first = json.loads(result_files[0].read_text(encoding="utf-8"))
                first["status"] = "failed"
                result_files[0].write_text(
                    json.dumps(first, ensure_ascii=False), encoding="utf-8")
            elif defect == "false_binding_label":
                first = json.loads(result_files[0].read_text(encoding="utf-8"))
                first["labels"] = [{"name": "ALLURE_ID",
                                    "value": str(C.FALSE_BINDING_ID)}]
                result_files[0].write_text(
                    json.dumps(first, ensure_ascii=False), encoding="utf-8")
            elif defect == "missing_head_binding_label":
                first = json.loads(result_files[0].read_text(encoding="utf-8"))
                first["labels"] = []
                result_files[0].write_text(
                    json.dumps(first, ensure_ascii=False), encoding="utf-8")
            elif defect == "multiple_binding_labels":
                first = json.loads(result_files[0].read_text(encoding="utf-8"))
                first["labels"] = [
                    {"name": "ALLURE_ID", "value": str(C.BINDINGS[C.SCENARIO_IDS[0]])},
                    {"name": "as_id", "value": str(C.FALSE_BINDING_ID)},
                ]
                result_files[0].write_text(
                    json.dumps(first, ensure_ascii=False), encoding="utf-8")
        with allure.step("Проверить блокировку импорта"):
            outcome = orchestrator.import_execution(C.EXECUTION_HEAD)
            assert outcome["outcome"] == "blocked"
            assert project.workflow_state()["phase"] == "implementation_ready"

    @allure.title("Санитизированный боевой контракт CAT-UPD-VAL сопоставляет "
                  "6 head passed и 4 base failed без scenario ID в display name")
    def test_sanitized_pilot_raw_allure_compatibility(self, tmp_path):
        with allure.step("Собрать санитизированные head (6 passed) и base "
                         "(4 failed) директории по боевому контракту"):
            pilot_orch = Orchestrator(tmp_path)
            pilot_sids = [*cat_consts.INVALID_IDS, *cat_consts.VALID_IDS]
            state = {"artifacts": {"scenarios": {"scenario_ids": pilot_sids}}}
            head_dir = tmp_path / "run-pilot-head"
            base_dir = tmp_path / "run-pilot-base"
            for target_dir, sids, status, with_ids in (
                (head_dir, pilot_sids, "passed", True),
                (base_dir, list(cat_consts.INVALID_IDS), "failed", False),
            ):
                target_dir.mkdir(parents=True)
                counts = ({"total": 6, "passed": 6, "failed": 0,
                           "errors": 0, "skipped": 0}
                          if status == "passed"
                          else {"total": 4, "passed": 0, "failed": 4,
                                "errors": 0, "skipped": 0})
                pairs = [
                    utils.junit_case_name(sid, pilot_orch._scenario_contract.index)
                    for sid in sids
                ]
                utils.junit_xml(
                    target_dir / "junit.xml", counts,
                    names=[p[0] for p in pairs],
                    classnames=[p[1] for p in pairs])
                titles = {
                    sid: (C.PILOT_INVALID_TITLE
                          if sid in cat_consts.INVALID_IDS
                          else C.PILOT_VALID_TITLE)
                    for sid in sids
                }
                bindings = ({sid: int(tid)
                             for sid, tid in
                             cat_consts.TESTOPS_ALLURE_IDS.items()}
                            if with_ids else None)
                utils.write_raw_allure_results(
                    target_dir / "allure-results",
                    {sid: status for sid in sids},
                    bindings=bindings,
                    index=pilot_orch._scenario_contract.index,
                    titles=titles)
        with allure.step("Проверить боевой _composition_problems на head и base"):
            head_manifest = {
                "environment": {"declared": {
                    "app_base_sha": C.APP_BASE_SHA,
                    "app_patch_sha256": C.APP_PATCH_SHA256}},
                "artifacts": {"allure_results": "allure-results",
                              "junit": "junit.xml"},
            }
            base_manifest = {
                "environment": {"declared": {"app_base_sha": C.APP_BASE_SHA}},
                "artifacts": {"allure_results": "allure-results",
                              "junit": "junit.xml"},
            }
            base_state = {
                "input": {"identity": {"app_base_sha": C.APP_BASE_SHA},
                          "revision_data": {"app_head": {
                              "kind": "patch", "sha256": C.APP_PATCH_SHA256,
                              "git_sha": None}}},
                "artifacts": state["artifacts"],
            }
            assert pilot_orch._composition_problems(
                state, head_manifest, head_dir) == []
            assert pilot_orch._composition_problems(
                base_state, base_manifest, base_dir) == []

    @allure.title("accept bindings отклоняет маппинг, противоречащий "
                  "ALLURE_ID уже записанного head execution")
    def test_accept_bindings_rejects_contradiction_with_recorded_head(
            self, project):
        with allure.step("Импортировать head execution с метками C.BINDINGS"):
            orch = project.drive_to_implementation_ready()
            utils.write_manifest(
                project.root, C.EXECUTION_HEAD, C.HEAD_JUNIT, 0,
                declared={"app_base_sha": C.APP_BASE_SHA,
                          "app_patch_sha256": C.APP_PATCH_SHA256})
            outcome = orch.import_execution(C.EXECUTION_HEAD)
            assert outcome["outcome"] == "imported"
        with allure.step("Попытка принять конфликтующие bindings блокируется"):
            wrong_map = dict(C.BINDINGS)
            wrong_map[C.SCENARIO_IDS[0]] = C.FALSE_BINDING_ID
            bad_env = project.envelope(
                "bindings", {"mapping": wrong_map, "source": "assign"},
                name="bindings-contradict.json")
            with pytest.raises(WorkflowBlockedError):
                orch.accept("bindings", bad_env)

    @allure.title("Baseline с error/broken вместо expected assertion failure "
                  "отклоняется")
    def test_baseline_errors_not_accepted_as_expected_failures(self, project):
        with allure.step("Создать baseline с junit errors вместо failed"):
            orch = project.drive_to_implementation_ready()
            err_counts = {"total": 2, "passed": 0, "failed": 0,
                          "errors": 2, "skipped": 0}
            pairs = [utils.junit_case_name(sid) for sid in C.BASE_SCENARIO_IDS]
            evidence = utils.write_manifest(
                project.root, C.EXECUTION_BASE, err_counts, 1,
                declared={"app_base_sha": C.APP_BASE_SHA},
                names=[p[0] for p in pairs])
            utils.write_raw_allure_results(
                evidence / "allure-results",
                {sid: "broken" for sid in C.BASE_SCENARIO_IDS})
        with allure.step("Импорт блокируется"):
            outcome = orch.import_execution(C.EXECUTION_BASE)
            assert outcome["outcome"] == "blocked"


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("R2: Git commit head отдельно от patch и dirty snapshot")
@allure.severity(allure.severity_level.BLOCKER)
class TestR2GitHeadSeparation:
    @allure.title("app kind=patch не подставляет patch digest в head_sha и "
                  "блокирует pr create даже при эхо транспортом")
    def test_patch_head_stays_draft_and_blocks_create(self, project):
        with allure.step("Довести patch-проект до executed"):
            project.drive_to_executed()
            transport = project.fake_pr_for("app")
            orch = project.orchestrator(pr_transports={"app": transport})
        with allure.step("pr prepare создаёт только локальный черновик"):
            prep = orch.pr_prepare(
                "app", title="patch draft", head_branch="wf/patch",
                base_branch="main", files=[C.CHANGED_APP_FILE])
            spec = project.workflow_state()["publications"]["pr"]["app"]["spec"]
            assert prep["outcome"] == "prepared" and prep["draft"] is True
            assert spec["head_sha"] is None
            assert spec["head_sha"] != C.APP_PATCH_SHA256
        with allure.step("pr create заблокирован до вызова транспорта"):
            result = orch.pr_create("app", execute=True, online=True)
            assert result["outcome"] == "blocked" and result["exit"] == 69
            assert transport.calls == []
            assert project.workflow_state()["publications"]["pr"]["app"][
                "status"] == "pending"

    @allure.title("Даже при подмене spec.head_sha на patch digest транспорт "
                  "не может перевести PR в verified")
    def test_tampered_patch_digest_in_spec_cannot_verify(self, project):
        with allure.step("Подготовить черновик и внедрить patch digest в spec"):
            project.drive_to_executed()
            orch0 = project.orchestrator()
            orch0.pr_prepare("app", title="patch", head_branch="wf/p",
                             base_branch="main")
            wf_dir = next(p for p in project.store_dir.iterdir() if p.is_dir())
            raw = json.loads((wf_dir / "state.json").read_text(encoding="utf-8"))
            raw["publications"]["pr"]["app"]["spec"]["head_sha"] = (
                C.APP_PATCH_SHA256)
            (wf_dir / "state.json").write_text(
                json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        with allure.step("Транспорт эхом возвращает тот же patch digest"):
            spec = raw["publications"]["pr"]["app"]["spec"]
            echo_ref = adapters.PrRef(
                repo=spec["repo"], number=55,
                url="https://git.invalid/pr/55", title=spec["title"],
                head_branch=spec["head_branch"],
                base_branch=spec["base_branch"],
                head_sha=C.APP_PATCH_SHA256,
                body_sha256=spec["body_sha256"],
                files=list(spec["files"]))
            transport = adapters.FakePrTransport(
                search_result=[echo_ref], create_result=echo_ref,
                get_map={(spec["repo"], 55): echo_ref})
            orch = project.orchestrator(pr_transports={"app": transport})
            outcome = orch.pr_create("app", execute=True, online=True)
        with allure.step("Проверить блокировку и отсутствие verified"):
            assert outcome["outcome"] == "blocked" and outcome["exit"] == 69
            assert transport.calls == []
            assert project.workflow_state()["publications"]["pr"]["app"][
                "status"] != "verified"

    @allure.title("Dirty QA head оставляет tests PR черновиком и блокирует "
                  "create")
    def test_dirty_tests_head_blocks_pr_create(self, project):
        with allure.step("Инициализировать проект с dirty tests checkout"):
            project.commit_app_head(C.APP_HEAD_COMMIT_SHA)
            project.tests_git.dirty = True
            snap = adapters.snapshot_allowlist(
                project.root, harness_mod.API_SOURCE_FILES)
            orch = project.drive_to_implementation_ready(
                app_head_kind="commit",
                app_head_git_sha=C.APP_HEAD_COMMIT_SHA,
                app_head_sha256=None,
                tests_dirty=True, tests_snapshot_sha256=snap)
            orch.accept("bindings", project.bindings_envelope())
            utils.harness_run(
                project.runner, project.root, C.EXECUTION_HEAD,
                C.HEAD_JUNIT, 0,
                declared={"app_base_sha": C.APP_HEAD_COMMIT_SHA},
                tests_dirty=True)
            orch.run_execution("head")
            utils.write_manifest(
                project.root, C.EXECUTION_BASE, C.BASE_JUNIT, 1,
                declared={"app_base_sha": C.APP_BASE_SHA},
                tests_dirty=True)
            orch.import_execution(C.EXECUTION_BASE)
        with allure.step("pr prepare для dirty tests не записывает commit SHA"):
            transport = project.fake_pr_for("tests")
            orch_pr = project.orchestrator(pr_transports={"tests": transport})
            prep = orch_pr.pr_prepare(
                "tests", title="dirty qa", head_branch="wf/qa",
                base_branch="main")
            spec = project.workflow_state()["publications"]["pr"]["tests"][
                "spec"]
            assert prep["draft"] is True and spec["head_sha"] is None
        with allure.step("pr create для dirty tests заблокирован"):
            outcome = orch_pr.pr_create("tests", execute=True, online=True)
            assert outcome["outcome"] == "blocked" and outcome["exit"] == 69
            assert transport.calls == []

    @allure.title("Override --head-sha проверяет тип Git-объекта, ревизию "
                  "и состав дерева")
    @pytest.mark.parametrize("bad_Case", (
        "missing_object", "blob_object", "base_commit",
        "wrong_tree_commit", "override_on_patch_revision",
        "mismatched_declared_files",
    ))
    def test_head_sha_override_rejects_invalid_commits(self, project,
                                                       bad_Case):
        with allure.step("Подготовить проект в фазе executed"):
            if bad_Case == "override_on_patch_revision":
                project.commit_app_head(C.APP_HEAD_COMMIT_SHA)
                project.drive_to_executed()
                orch = project.orchestrator()
                outcome = orch.pr_prepare(
                    "app", title="override on patch", head_branch="wf/h",
                    base_branch="main", head_sha=C.APP_HEAD_COMMIT_SHA)
                assert outcome["outcome"] == "blocked"
                assert outcome["exit"] == 69
                return
            if bad_Case == "wrong_tree_commit":
                project.git.head = C.WRONG_TREE_COMMIT_SHA
                project.git.dirty = False
                orch = project.drive_to_implementation_ready(
                    app_head_kind="commit",
                    app_head_git_sha=C.WRONG_TREE_COMMIT_SHA,
                    app_head_sha256=None)
                orch.accept("bindings", project.bindings_envelope())
                utils.harness_run(
                    project.runner, project.root, C.EXECUTION_HEAD,
                    C.HEAD_JUNIT, 0,
                    declared={"app_base_sha": C.WRONG_TREE_COMMIT_SHA})
                orch.run_execution("head")
                utils.write_manifest(
                    project.root, C.EXECUTION_BASE, C.BASE_JUNIT, 1,
                    declared={"app_base_sha": C.APP_BASE_SHA})
                orch.import_execution(C.EXECUTION_BASE)
                outcome = orch.pr_prepare(
                    "app", title="wrong tree", head_branch="wf/h",
                    base_branch="main")
                assert outcome["outcome"] == "blocked"
                assert outcome["exit"] == 69
                return
            orch = project.drive_commit_to_executed()
        with allure.step(f"Проверить отказ --head-sha ({bad_Case})"):
            target_sha = {
                "missing_object": C.MISSING_COMMIT_SHA,
                "blob_object": C.NON_COMMIT_OBJECT_SHA,
                "base_commit": C.APP_BASE_SHA,
                "mismatched_declared_files": C.APP_HEAD_COMMIT_SHA,
            }[bad_Case]
            files = (["src/main/Dto.java"]
                     if bad_Case == "mismatched_declared_files"
                     else [C.CHANGED_APP_FILE])
            outcome = orch.pr_prepare(
                "app", title="bad override", head_branch="wf/h",
                base_branch="main", files=files, head_sha=target_sha)
            assert outcome["outcome"] == "blocked"
            assert outcome["exit"] == 69

    @allure.title("State schema отвергает published при patch head или dirty "
                  "tests")
    def test_state_schema_rejects_published_without_clean_commits(self,
                                                                  tmp_path):
        with allure.step("Сформировать поддельный published state на patch"):
            proj = utils.Project(tmp_path / "p")
            proj.drive_commit_to_executed()
            proj.publish_handlers()
            orch = proj.orchestrator(
                pr_transports={r: proj.fake_pr_for(r)
                               for r in ("app", "tests")})
            orch.publish_testops(C.EXECUTION_HEAD, execute=True)
            for role in ("app", "tests"):
                orch.pr_prepare(
                    role, title="ok", head_branch="wf/h", base_branch="main",
                    files=([C.CHANGED_APP_FILE] if role == "app" else []))
                orch.pr_create(role, execute=True, online=True)
            wf_dir = next(p for p in proj.store_dir.iterdir() if p.is_dir())
            raw = json.loads((wf_dir / "state.json").read_text(encoding="utf-8"))
            assert raw["phase"] == "published"
            raw["input"]["revision_data"]["app_head"] = {
                "kind": "patch", "sha256": C.APP_PATCH_SHA256, "git_sha": None}
            tampered_dir = tmp_path / "tampered"
            tampered_dir.mkdir()
            (tampered_dir / "state.json").write_text(
                json.dumps(raw), encoding="utf-8")
        with allure.step("Проверить отказ load_state"):
            with pytest.raises(WorkflowSchemaError):
                state_mod.load_state(tampered_dir)

    @allure.title("Read-only GitReadAdapter проверяет реальные commit/blob "
                  "объекты без записей")
    def test_real_git_read_adapter_object_and_tree(self):
        with allure.step("Прочитать HEAD текущего репозитория read-only"):
            repo_root = Path(__file__).resolve().parents[2]
            git = adapters.GitReadAdapter(repo_root)
            head = git.head_commit()
            assert head is not None
            assert git.object_type(head) == "commit"
            assert git.object_type(C.MISSING_COMMIT_SHA) is None
        with allure.step("Проверить blob объекта != commit и чтение дерева"):
            req_blob = git.commit_blob(head, "conftest.py")
            assert req_blob is not None
            assert git.object_type(req_blob) == "blob"
            assert git.commit_file_sha256(head, "conftest.py") is not None

    @allure.title("Непроверяемый non-git каталог и CLI --head-sha возвращают "
                  "код 69")
    def test_unverifiable_non_git_and_cli_head_sha_exit_69(self, project,
                                                           tmp_path):
        with allure.step("Non-git app checkout не подтверждает commit SHA"):
            project.commit_app_head(C.APP_HEAD_COMMIT_SHA)
            orch_setup = project.drive_commit_to_executed()
            assert orch_setup is not None
            real_non_git = adapters.GitReadAdapter(project.app_repo)
            orch_non_git = project.orchestrator(git_adapter=real_non_git)
            blocked = orch_non_git.pr_prepare(
                "app", title="unverifiable", head_branch="wf/h",
                base_branch="main")
            assert blocked["outcome"] == "blocked" and blocked["exit"] == 69
        with allure.step("CLI pr prepare с ложным --head-sha завершается 69"):
            repo_root = Path(__file__).resolve().parents[2]
            real_git = adapters.GitReadAdapter(repo_root)
            head = real_git.head_commit()
            dirty_flag = ("--tests-dirty" if real_git.is_dirty()
                          else "--tests-clean")
            cli_store = tmp_path / "cli-store"
            cli = [sys.executable, str(repo_root / "tools" / "workflow.py"),
                   "--store-dir", str(cli_store)]
            init_res = subprocess.run(
                [*cli, "init", "--pilot-id", C.PILOT_ID,
                 "--app-repo", C.APP_REPO, "--app-base-sha", head,
                 "--app-patch-sha256", C.APP_PATCH_SHA256,
                 "--tests-commit", head, dirty_flag,
                 "--app-repo-path", str(repo_root),
                 "--requirements", str(project.root / C.REQUIREMENTS_REL)],
                cwd=repo_root, capture_output=True, text=True, timeout=60)
            assert init_res.returncode == 0, init_res.stderr
            prep_res = subprocess.run(
                [*cli, "pr", "prepare", "--repo", "app", "--title", "t",
                 "--head-branch", "wf/h", "--base-branch", "main",
                 "--head-sha", C.MISSING_COMMIT_SHA],
                cwd=repo_root, capture_output=True, text=True, timeout=60)
            assert prep_res.returncode == 69


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("R3: проверяемая историческая baseline provenance без обхода")
@allure.severity(allure.severity_level.BLOCKER)
class TestR3HistoricalProvenance:
    @allure.title("Для head с чужим tests commit или без source_identity "
                  "--provenance никогда не разрешает импорт")
    def test_head_rejects_any_provenance_waiver(self, project):
        with allure.step("Создать head manifest с чужим commit и без sources"):
            orchestrator = project.drive_to_implementation_ready()
            utils.write_manifest(
                project.root, C.EXECUTION_HEAD, C.HEAD_JUNIT, 0,
                declared={"app_base_sha": C.APP_BASE_SHA,
                          "app_patch_sha256": C.APP_PATCH_SHA256},
                tests_commit=C.TESTS_COMMIT_2, source_files=None)
        with allure.step("Попытка импорта с legacy waiver отклоняется"):
            legacy = {"tests_commit": C.TESTS_COMMIT_2,
                      "source_identity_missing": True}
            outcome = orchestrator.import_execution(
                C.EXECUTION_HEAD, provenance=legacy)
            assert outcome["outcome"] == "blocked"
        with allure.step("Даже полный provenance record для head запрещён"):
            review_doc = utils.write_doc(
                project.root, C.REVIEW_WAVE_REL, C.REVIEW_WAVE_TEXT)
            valid_head = utils.write_manifest(
                project.root, C.EXECUTION_OTHER, C.HEAD_JUNIT, 0,
                declared={"app_base_sha": C.APP_BASE_SHA,
                          "app_patch_sha256": C.APP_PATCH_SHA256},
                tests_commit=C.TESTS_COMMIT_2)
            cur_sha = utils.sha256_file(project.root / C.TEST_FILES[0])
            forged = _make_baseline_acceptance(
                project, valid_head, review_doc=review_doc,
                historical_sha=cur_sha, current_sha=cur_sha)
            forged["variant"] = "head"
            orch2 = project.orchestrator(accepted_provenance=(forged,))
            outcome2 = orch2.import_execution(
                C.EXECUTION_OTHER, provenance=forged)
            assert outcome2["outcome"] == "blocked"

    @allure.title("Положительный принятый baseline acceptance record и блокировка "
                  "поддельных/неполных/изменённых записей")
    @pytest.mark.parametrize("tamper", (
        None, "no_provenance", "unregistered_self_signed",
        "wrong_execution_id", "wrong_manifest_sha", "wrong_junit_sha",
        "wrong_allure_sha", "missing_review_doc", "drifted_review_doc",
        "outside_contract_scope", "checkout_drifted_after_acceptance",
        "source_identity_missing_flag",
    ))
    def test_baseline_acceptance_record_matrix(self, project, tamper):
        with allure.step("Сформировать исторический baseline до правки теста"):
            test_path = project.root / C.TEST_FILES[0]
            test_path.write_text(C.HISTORICAL_TEST_CONTENT, encoding="utf-8")
            historical_sha = utils.sha256_file(test_path)
            evidence = utils.write_manifest(
                project.root, C.EXECUTION_BASE, C.BASE_JUNIT, 1,
                declared={"app_base_sha": C.APP_BASE_SHA},
                tests_commit=C.TESTS_COMMIT_2)
            test_path.write_text(C.TEST_FILE_CONTENT, encoding="utf-8")
            current_sha = utils.sha256_file(test_path)
            review_doc = utils.write_doc(
                project.root, C.REVIEW_WAVE_REL, C.REVIEW_WAVE_TEXT)
            project.sync_tests_commit(C.TESTS_COMMIT)
            accepted_record = _make_baseline_acceptance(
                project, evidence, review_doc=review_doc,
                historical_sha=historical_sha, current_sha=current_sha)

        with allure.step(f"Применить вариант проверки: {tamper or 'valid'}"):
            passed_record = copy.deepcopy(accepted_record)
            registry = (accepted_record,)
            if tamper == "no_provenance":
                passed_record = None
            elif tamper == "unregistered_self_signed":
                registry = ()
            elif tamper == "wrong_execution_id":
                passed_record["execution_id"] = C.EXECUTION_OTHER
            elif tamper == "wrong_manifest_sha":
                passed_record["manifest_sha256"] = "0" * 64
                registry = (copy.deepcopy(passed_record),)
            elif tamper == "wrong_junit_sha":
                passed_record["junit_sha256"] = "0" * 64
                registry = (copy.deepcopy(passed_record),)
            elif tamper == "wrong_allure_sha":
                passed_record["allure_results_sha256"] = "0" * 64
                registry = (copy.deepcopy(passed_record),)
            elif tamper == "missing_review_doc":
                (project.root / C.REVIEW_WAVE_REL).unlink()
            elif tamper == "drifted_review_doc":
                (project.root / C.REVIEW_WAVE_REL).write_text(
                    "# tampered review\n", encoding="utf-8")
            elif tamper == "outside_contract_scope":
                passed_record["equivalence_scope"]["allowed_changed_files"][
                    "docs/scenarios.md"] = {
                    "historical_sha256": "1" * 64,
                    "current_sha256": "2" * 64,
                    "reason": "out of contract scope",
                }
                registry = (copy.deepcopy(passed_record),)
            elif tamper == "checkout_drifted_after_acceptance":
                passed_record["equivalence_scope"]["allowed_changed_files"][
                    C.TEST_FILES[0]]["current_sha256"] = "9" * 64
                registry = (copy.deepcopy(passed_record),)
            elif tamper == "source_identity_missing_flag":
                passed_record["source_identity_missing"] = True
                registry = (copy.deepcopy(passed_record),)

            orch = project.orchestrator(accepted_provenance=registry)
            project.drive_to_implementation_ready(orch)
            outcome = orch.import_execution(
                C.EXECUTION_BASE, provenance=passed_record)

        with allure.step("Проверить ожидаемый исход"):
            if tamper is None:
                assert outcome["outcome"] == "imported"
                assert outcome["variant"] == "base"
                assert outcome["bound_revision"] == 1
            else:
                assert outcome["outcome"] == "blocked", outcome


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("R4: durable checkpoints plan/assign/package без лишних повторов")
@allure.severity(allure.severity_level.BLOCKER)
class TestR4TestOpsCheckpoints:
    def _results_dir(self, project):
        return (project.root / "artifacts" / "harness" / C.EXECUTION_HEAD
                / "allure-results")

    @allure.title("Повтор prepare готового execution — no-op с нулём dispatch")
    def test_repeat_prepare_is_zero_dispatch_noop(self, project):
        with allure.step("Выполнить первый prepare-testops"):
            orch = project.drive_to_executed()
            utils.testops_local_handlers(
                project.runner, project.root, C.EXECUTION_HEAD,
                self._results_dir(project), dict(C.BINDINGS))
            first = orch.prepare_testops(C.EXECUTION_HEAD)
            assert first["outcome"] == "prepared"
            assert first["steps_run"] == ["plan", "assign", "package"]
            assert _tool_actions(project.runner) == [
                "plan", "assign", "package"]
        with allure.step("Повторить prepare-testops и убедиться в 0 вызовов"):
            before = len(project.runner.calls)
            second = orch.prepare_testops(C.EXECUTION_HEAD)
            assert second["outcome"] == "no-op"
            assert second["steps_skipped"] == ["plan", "assign", "package"]
            assert len(project.runner.calls) == before

    @allure.title("Crash после plan возобновляет только assign и package")
    def test_crash_after_plan_skips_plan_on_resume(self, project):
        with allure.step("Сымитировать сбой на шаге assign после успеха plan"):
            orch = project.drive_to_executed()
            utils.testops_local_handlers(
                project.runner, project.root, C.EXECUTION_HEAD,
                self._results_dir(project), dict(C.BINDINGS))
            fail_once = {"assign": True}

            def flaky_assign(argv, line):
                if fail_once["assign"]:
                    fail_once["assign"] = False
                    return adapters.RunOutcome(1)
                return None

            utils.on_testops(project.runner, "assign", flaky_assign)
            first = orch.prepare_testops(C.EXECUTION_HEAD)
            assert first["outcome"] == "failed" and first["step"] == "assign"
            assert _tool_actions(project.runner) == ["plan", "assign"]
        with allure.step("Повторный prepare пропускает plan и доделывает "
                         "assign + package"):
            before = len(project.runner.tool_calls("tools/run-testops.sh"))
            second = orch.prepare_testops(C.EXECUTION_HEAD)
            assert second["outcome"] == "prepared"
            assert second["steps_skipped"] == ["plan"]
            assert second["steps_run"] == ["assign", "package"]
            resumed = [
                a for argv in project.runner.tool_calls(
                    "tools/run-testops.sh")[before:]
                for a in ("plan", "assign", "package") if a in argv
            ]
            assert resumed == ["assign", "package"]

    @allure.title("Crash после assign возобновляет только package")
    def test_crash_after_assign_skips_plan_and_assign(self, project):
        with allure.step("Сымитировать сбой на шаге package"):
            orch = project.drive_to_executed()
            utils.testops_local_handlers(
                project.runner, project.root, C.EXECUTION_HEAD,
                self._results_dir(project), dict(C.BINDINGS))
            fail_once = {"package": True}

            def flaky_package(argv, line):
                if fail_once["package"]:
                    fail_once["package"] = False
                    return adapters.RunOutcome(1)
                return None

            utils.on_testops(project.runner, "package", flaky_package)
            first = orch.prepare_testops(C.EXECUTION_HEAD)
            assert first["outcome"] == "failed" and first["step"] == "package"
        with allure.step("Повторный prepare вызывает только package"):
            before = len(project.runner.tool_calls("tools/run-testops.sh"))
            second = orch.prepare_testops(C.EXECUTION_HEAD)
            assert second["outcome"] == "prepared"
            assert second["steps_skipped"] == ["plan", "assign"]
            assert second["steps_run"] == ["package"]
            resumed = [
                a for argv in project.runner.tool_calls(
                    "tools/run-testops.sh")[before:]
                for a in ("plan", "assign", "package") if a in argv
            ]
            assert resumed == ["package"]

    @allure.title("Потерянный save workflow после успеха package "
                  "восстанавливается без пересборки пакета")
    def test_lost_workflow_save_after_package_recovers_without_rebuild(
            self, project):
        with allure.step("Создать полностью собранный пакет в execution state "
                         "без записи testops_prepare в workflow state"):
            orch = project.drive_to_executed()
            utils.make_testops_state(
                project.root, C.EXECUTION_HEAD, upload_status="pending",
                with_package=True, results_dir=self._results_dir(project))
            exec_entry = next(
                e for e in project.workflow_state()["executions"]
                if e["execution_id"] == C.EXECUTION_HEAD)
            assert "testops_prepare" not in exec_entry
        with allure.step("prepare-testops восстанавливает checkpoint из "
                         "execution state без единого subprocess dispatch"):
            outcome = orch.prepare_testops(C.EXECUTION_HEAD)
            assert outcome["outcome"] == "no-op"
            assert outcome["recovered"] is True
            assert project.runner.tool_calls("tools/run-testops.sh") == []
            saved_cp = next(
                e for e in project.workflow_state()["executions"]
                if e["execution_id"] == C.EXECUTION_HEAD)["testops_prepare"]
            assert saved_cp["package"] == "completed"
            assert saved_cp["package_sha256"] is not None

    @allure.title("Смена локальных pending-данных пересобирает только "
                  "инвалидированный шаг; attempted/uploaded неизменяемы")
    @pytest.mark.parametrize("immutable_status", (
        "in_progress", "sent", "uploaded", "unknown", "failed",
    ))
    def test_pending_invalidation_and_attempted_immutability(
            self, project, immutable_status):
        with allure.step("Подготовить pending пакет и повредить только пакет"):
            orch = project.drive_to_executed()
            utils.testops_local_handlers(
                project.runner, project.root, C.EXECUTION_HEAD,
                self._results_dir(project), dict(C.BINDINGS))
            orch.prepare_testops(C.EXECUTION_HEAD)
            pkg_dir = (project.root / "artifacts" / "testops"
                       / C.EXECUTION_HEAD / C.PACKAGE_DIR_NAME)
            (pkg_dir / "corrupt.tmp").write_text("drift", encoding="utf-8")
            before = len(project.runner.tool_calls("tools/run-testops.sh"))
            rebuilt = orch.prepare_testops(C.EXECUTION_HEAD)
            assert rebuilt["outcome"] == "prepared"
            assert rebuilt["steps_skipped"] == ["plan", "assign"]
            assert rebuilt["steps_run"] == ["package"]
            assert len(project.runner.tool_calls(
                "tools/run-testops.sh")) - before == 1
        with allure.step(f"Перевести execution в {immutable_status} с attempts=1"):
            state_dir = (project.root / "artifacts" / "testops"
                         / C.EXECUTION_HEAD)
            st = tstate.load_state(state_dir)
            st["upload"]["status"] = immutable_status
            st["upload"]["attempts"] = 1
            tstate.save_state(state_dir, st)
            sha_before = utils.testops_state_sha(project.root, C.EXECUTION_HEAD)
            calls_before = len(project.runner.calls)
        with allure.step("prepare-testops блокируется, state байт-идентичен"):
            with pytest.raises(WorkflowBlockedError):
                orch.prepare_testops(C.EXECUTION_HEAD)
            assert len(project.runner.calls) == calls_before
            assert utils.testops_state_sha(
                project.root, C.EXECUTION_HEAD) == sha_before

    @allure.title("Успех subprocess plan/assign/package с крашем процесса до "
                  "workflow save восстанавливается без повтора готовых шагов")
    @pytest.mark.parametrize("crash_step,expected_resumed", (
        ("plan", ["assign", "package"]),
        ("assign", ["package"]),
        ("package", []),
    ))
    def test_subprocess_succeeds_then_crash_before_workflow_save(
            self, project, crash_step, expected_resumed):
        with allure.step(f"Настроить краш сразу после записи {crash_step}"):
            orch = project.drive_to_executed()
            results_dir = self._results_dir(project)
            utils.testops_local_handlers(
                project.runner, project.root, C.EXECUTION_HEAD,
                results_dir, dict(C.BINDINGS))
            base_handlers = list(project.runner.handlers)
            crashed = {"done": False}

            def succeed_then_die(argv, line):
                if crashed["done"]:
                    return None
                crashed["done"] = True
                for pred, handler in reversed(base_handlers):
                    if pred(argv):
                        handler(argv, line)
                        break
                raise RuntimeError(f"died after {crash_step} subprocess")

            utils.on_testops(project.runner, crash_step, succeed_then_die)
            with pytest.raises(RuntimeError):
                orch.prepare_testops(C.EXECUTION_HEAD)
        with allure.step("Возобновить prepare-testops и проверить точные "
                         "вызовы"):
            before = len(project.runner.tool_calls("tools/run-testops.sh"))
            resumed = orch.prepare_testops(C.EXECUTION_HEAD)
            dispatched = [
                a for argv in project.runner.tool_calls(
                    "tools/run-testops.sh")[before:]
                for a in ("plan", "assign", "package") if a in argv
            ]
            assert dispatched == expected_resumed
            if expected_resumed:
                assert resumed["outcome"] == "prepared"
            else:
                assert resumed["outcome"] == "no-op"
                assert resumed["recovered"] is True

    @allure.title("Смена raw allure-results у pending execution инвалидирует "
                  "plan/assign/package и пересобирает их")
    def test_changed_source_results_invalidates_pending_prepare(self, project):
        with allure.step("Выполнить первичный prepare-testops"):
            orch = project.drive_to_executed()
            results_dir = self._results_dir(project)
            utils.testops_local_handlers(
                project.runner, project.root, C.EXECUTION_HEAD,
                results_dir, dict(C.BINDINGS))
            first = orch.prepare_testops(C.EXECUTION_HEAD)
            assert first["outcome"] == "prepared"
        with allure.step("Обновить вложение в allure-results при pending"):
            (results_dir / "note.txt").write_text("fresh local note\n",
                                                  encoding="utf-8")
            before = len(project.runner.tool_calls("tools/run-testops.sh"))
            second = orch.prepare_testops(C.EXECUTION_HEAD)
        with allure.step("Проверить инвалидацию plan и пересборку пакета"):
            assert second["outcome"] == "prepared"
            assert "plan" in second["steps_run"]
            assert "package" in second["steps_run"]
            assert len(project.runner.tool_calls(
                "tools/run-testops.sh")) > before

