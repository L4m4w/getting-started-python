"""Регрессии 21R-A: schema-валидация state, publications gate, TestOps ID.

Findings 21A: F-21A-1 (непроверенные типы expected_executions/
strength_evidence/junit_summary/selection давали AttributeError вместо
clean 69), F-21A-2 (ослабленный состав publications допускал published),
F-21A-5 (True принимался как TestOps ID). Проверки только offline.
"""
import copy
import json
import subprocess
import sys
from pathlib import Path

import allure
import pytest

from infrastructure.workflow import envelopes, state as state_mod
from test_data.consts import workflow as C
from test_data.consts import workflow_21r_a as C21
from test_data.utils import workflow as utils

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_CLI = REPO_ROOT / "tools" / "workflow.py"


@pytest.fixture
def project(tmp_path):
    return utils.Project(tmp_path / "proj")


def _revision_data(**overrides):
    data = {
        "app_head": {"kind": "patch", "sha256": C.APP_PATCH_SHA256,
                     "git_sha": None},
        "tests_repo": {"commit": C.TESTS_COMMIT, "dirty": False,
                       "snapshot_sha256": None},
        "requirements": {"path": C.REQUIREMENTS_REL, "version": "1",
                         "sha256": "0" * 64, "ids": list(C.REQUIREMENT_IDS)},
        "expected_executions": C.EXPECTED_EXECUTIONS,
        "strength_evidence": C.STRENGTH_EVIDENCE,
    }
    data.update(overrides)
    return data


def _state_dir(project):
    return next(path for path in project.store_dir.iterdir()
                if path.is_dir()
                and state_mod.WORKFLOW_ID_RE.fullmatch(path.name))


def _rewrite_state(state_dir, mutate):
    path = state_dir / "state.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def _forge_published(data):
    """Довести executed-state до внутренне согласованного published."""
    revision = data["input"]["revision"]
    head_exec = next(e for e in data["executions"]
                     if e["variant"] == "head"
                     and e["bound_revision"] == revision)
    pubs = data["publications"]
    pubs["testops"]["execution_id"] = head_exec["execution_id"]
    pubs["testops"]["last_observation"] = {
        "upload_status": "uploaded", "launch_id": 1,
        "checked_at": "2026-01-01T00:00:00+00:00",
        "state_sha256": "f" * 64}
    head_sha = data["input"]["revision_data"]["app_head"]["git_sha"]
    tests_sha = data["input"]["revision_data"]["tests_repo"]["commit"]
    for role, sha in (("app", head_sha), ("tests", tests_sha)):
        pubs["pr"][role].update(
            status="verified",
            spec={"head_sha": sha, "title": "x", "title_key": "x",
                  "head_branch": "h", "base_branch": "b",
                  "repo": role, "files": []},
            spec_sha256="a" * 64)
    data["phase"] = "published"


def _apply_tamper(data, path, op, value):
    node = data["publications"]
    for key in path[:-1]:
        node = node[key]
    if op == "delete":
        node.pop(path[-1], None)
    else:
        node[path[-1]] = value


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("21R-A: типы revision_data и executions в schema")
@allure.severity(allure.severity_level.CRITICAL)
class TestGateDataSchema:
    @allure.title("Повреждённый revision_data даёт clean schema error")
    @pytest.mark.parametrize(
        "name,key,value,fragment", C21.CORRUPT_REVISION_DATA,
        ids=[case[0] for case in C21.CORRUPT_REVISION_DATA])
    def test_corrupt_revision_data_rejected(self, project, name, key,
                                            value, fragment):
        project.drive_to_executed()
        with allure.step(f"Подменить {key} на повреждённое значение"):
            path = _rewrite_state(
                _state_dir(project),
                lambda d: d["input"]["revision_data"].update({key: value}))
            before = path.read_bytes()
        with allure.step("load_state отклоняет без traceback"):
            with pytest.raises(state_mod.WorkflowSchemaError,
                               match=fragment):
                state_mod.load_state(path.parent)
        assert path.read_bytes() == before

    @allure.title("Повреждённые поля executions[] дают clean schema error")
    @pytest.mark.parametrize(
        "name,field,value,fragment", C21.CORRUPT_EXECUTION_FIELDS,
        ids=[case[0] for case in C21.CORRUPT_EXECUTION_FIELDS])
    def test_corrupt_execution_fields_rejected(self, project, name, field,
                                               value, fragment):
        project.drive_to_executed()
        with allure.step(f"Подменить executions[0].{field}"):
            path = _rewrite_state(
                _state_dir(project),
                lambda d: d["executions"][0].update({field: value}))
            before = path.read_bytes()
        with allure.step("load_state отклоняет без traceback"):
            with pytest.raises(state_mod.WorkflowSchemaError,
                               match=fragment):
                state_mod.load_state(path.parent)
        assert path.read_bytes() == before

    @allure.title("Пустой expected_executions валиден схемой и fail-closed")
    def test_empty_expected_executions_fail_closed(self, project):
        project.drive_to_executed()
        state_dir = _state_dir(project)
        _rewrite_state(
            state_dir,
            lambda d: (d["input"]["revision_data"].update(
                expected_executions=[], strength_evidence={}),
                       d.update(phase="implementation_ready")))
        state = state_mod.load_state(state_dir)
        assert state["phase"] == "implementation_ready"
        assert state_mod.executions_satisfy(state) is False

    @allure.title("Прямые вызовы gate'ов не падают на malformed dict")
    def test_direct_gates_no_crash(self):
        req = {"variant": "head", "scope": "api", "expect": {"total": 1}}
        entry = {"status": "completed", "bound_revision": 1,
                 "variant": "head",
                 "junit_summary": {"total": 1, "passed": 1, "failed": 0,
                                   "errors": 0, "skipped": 0},
                 "selection": {"scope": "group",
                               "targets": ["tests/api"]}}
        assert state_mod.execution_matches(entry, req, 1) is True
        malformed = [
            (42, req), ("x", req), (None, req),
            (dict(entry, junit_summary="x"), req),
            (dict(entry, junit_summary=None), req),
            (dict(entry, selection="x"), req),
            (dict(entry, selection={"targets": "tests/api"}), req),
            (dict(entry, bound_revision=True), req),
            (entry, 42), (entry, dict(req, expect="x")),
            (dict(entry, bound_revision=2), req),
        ]
        for bad_entry, bad_req in malformed:
            assert state_mod.execution_matches(bad_entry, bad_req, 1) \
                is False
        assert state_mod.executions_satisfy({}) is False
        assert state_mod.executions_satisfy({"input": "x"}) is False
        assert state_mod.executions_satisfy(
            {"input": {"revision": 1, "revision_data": "x"}}) is False
        assert state_mod.publications_confirmed({}) is False
        assert state_mod.publications_confirmed(
            {"input": {"revision": 1, "revision_data": {}},
             "publications": "x"}) is False


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("21R-A: fixed-MVP состав publications")
@allure.severity(allure.severity_level.CRITICAL)
class TestPublicationsContract:
    @allure.title("Ослабленный/повреждённый состав отклоняется schema")
    @pytest.mark.parametrize(
        "name,path,op,value,gate", C21.PUBLICATION_TAMPERS,
        ids=[case[0] for case in C21.PUBLICATION_TAMPERS])
    def test_tampered_publications_rejected(self, project, name, path,
                                            op, value, gate):
        project.drive_commit_to_executed()
        with allure.step(f"Подделать published с tamper {name}"):
            state_path = _rewrite_state(
                _state_dir(project),
                lambda d: (_forge_published(d),
                           _apply_tamper(d, path, op, value)))
            before = state_path.read_bytes()
        with pytest.raises(state_mod.WorkflowSchemaError):
            state_mod.load_state(state_path.parent)
        assert state_path.read_bytes() == before

    @allure.title("required без JSON true отклоняется в каждой роли")
    @pytest.mark.parametrize("path", C21.WEAK_REQUIRED_PATHS,
                             ids=[".".join(p)
                                  for p in C21.WEAK_REQUIRED_PATHS])
    @pytest.mark.parametrize("value", C21.WEAK_REQUIRED_VALUES,
                             ids=repr)
    def test_weak_required_rejected(self, project, path, value):
        project.drive_commit_to_executed()
        state_path = _rewrite_state(
            _state_dir(project),
            lambda d: (_forge_published(d),
                       _apply_tamper(d, path, "set", value)))
        with pytest.raises(state_mod.WorkflowSchemaError):
            state_mod.load_state(state_path.parent)

    @allure.title("Прямой gate отклоняет ослабленный набор без schema")
    def test_direct_gate_rejects_weakened(self, project):
        project.drive_commit_to_executed()
        state_path = _state_dir(project) / "state.json"
        base = json.loads(state_path.read_text(encoding="utf-8"))
        _forge_published(base)
        with allure.step("Контроль: согласованный набор подтверждён"):
            assert state_mod.publications_confirmed(base) is True
        for name, path, op, value, gate in C21.PUBLICATION_TAMPERS:
            variant = copy.deepcopy(base)
            _apply_tamper(variant, path, op, value)
            assert state_mod.publications_confirmed(variant) is not gate, \
                name
        for path in C21.WEAK_REQUIRED_PATHS:
            for value in C21.WEAK_REQUIRED_VALUES:
                variant = copy.deepcopy(base)
                _apply_tamper(variant, path, "set", value)
                assert state_mod.publications_confirmed(variant) is False

    @allure.title("Внутренне согласованный published загружается")
    def test_consistent_published_loads(self, project):
        project.drive_commit_to_executed()
        state_dir = _state_dir(project)
        _rewrite_state(state_dir, _forge_published)
        state = state_mod.load_state(state_dir)
        assert state["phase"] == "published"


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("21R-A: домен TestOps ID в bindings")
@allure.severity(allure.severity_level.NORMAL)
class TestBindingsTestOpsId:
    @allure.title("bool/строка/float/неположительный ID отклоняется")
    @pytest.mark.parametrize("bad_id", C21.BAD_TESTOPS_IDS,
                             ids=repr)
    def test_bad_ids_rejected(self, project, bad_id):
        mapping = dict(C.BINDINGS)
        mapping[C.SCENARIO_IDS[0]] = bad_id
        env_path = project.envelope(
            "bindings", {"mapping": mapping, "source": "assign"},
            name=f"bindings-bad-{bad_id!r}.json")
        with pytest.raises(envelopes.EnvelopeError):
            envelopes.load_envelope(env_path)

    @allure.title("Bool ID блокируется на accept, артефакт не принимается")
    def test_bool_id_blocked_at_accept(self, project):
        orchestrator = project.drive_to_implementation_ready()
        mapping = dict(C.BINDINGS)
        mapping[C.SCENARIO_IDS[0]] = True
        env_path = project.envelope(
            "bindings", {"mapping": mapping, "source": "assign"},
            name="bindings-bool.json")
        with pytest.raises(state_mod.WorkflowValidationError):
            orchestrator.accept("bindings", env_path)
        assert (project.workflow_state()["artifacts"]["bindings"]["status"]
                == "pending")

    @allure.title("Положительные int ID, включая 1, валидны")
    def test_good_ids_accepted(self, project):
        for index, good_id in enumerate(C21.GOOD_TESTOPS_IDS):
            mapping = dict(C.BINDINGS)
            mapping[C.SCENARIO_IDS[0]] = good_id
            env_path = project.envelope(
                "bindings", {"mapping": mapping, "source": "assign"},
                name=f"bindings-good-{index}.json")
            env = envelopes.load_envelope(env_path)
            assert env["payload"]["mapping"][C.SCENARIO_IDS[0]] == good_id


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("21R-A: production CLI на испорченном state")
@allure.severity(allure.severity_level.CRITICAL)
class TestCliCorruptState:
    def _store_with_state(self, tmp_path):
        state = state_mod.new_state(
            pilot_id=C.PILOT_ID, app_repo=C.APP_REPO_KEY,
            app_base_sha=C.APP_BASE_SHA,
            revision_data=_revision_data())
        store = tmp_path / "store"
        workflow_dir = store / state["workflow_id"]
        state_mod.save_state(workflow_dir, state)
        return store, workflow_dir / "state.json"

    def _corrupt(self, state_path, kind):
        data = json.loads(state_path.read_text(encoding="utf-8"))
        if kind == "revision_data":
            data["input"]["revision_data"]["expected_executions"] = [42]
        else:
            data["publications"]["testops"]["required"] = False
        state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @allure.title("status на испорченной копии: exit 69, файл не меняется")
    @pytest.mark.parametrize("kind", ("revision_data", "publications"))
    def test_status_on_corrupt_state_exits_69(self, tmp_path, kind):
        store, state_path = self._store_with_state(tmp_path)
        self._corrupt(state_path, kind)
        before = state_path.read_bytes()
        with allure.step("Запустить production CLI status"):
            result = subprocess.run(
                [sys.executable, str(WORKFLOW_CLI),
                 "--store-dir", str(store), "status"],
                capture_output=True, text=True, timeout=60)
        assert result.returncode == 69
        assert "BLOCKED" in result.stderr
        assert "Traceback" not in result.stderr
        assert "AttributeError" not in result.stderr
        assert state_path.read_bytes() == before

    @allure.title("status на валидном state: exit 0")
    def test_status_on_valid_state(self, tmp_path):
        store, _ = self._store_with_state(tmp_path)
        result = subprocess.run(
            [sys.executable, str(WORKFLOW_CLI),
             "--store-dir", str(store), "status"],
            capture_output=True, text=True, timeout=60)
        assert result.returncode == 0
