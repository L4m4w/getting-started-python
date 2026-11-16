"""Схема состояния, index и каскад инвалидации оркестратора (offline)."""
import json

import allure
import pytest

from infrastructure.workflow import index as index_mod
from infrastructure.workflow import state as state_mod
from test_data.consts import workflow as C
from test_data.utils import workflow as utils


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


def _new_state(**kw):
    args = dict(pilot_id=C.PILOT_ID, app_repo=C.APP_REPO_KEY,
                app_base_sha=C.APP_BASE_SHA,
                revision_data=_revision_data())
    args.update(kw)
    return state_mod.new_state(**args)


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("Схема состояния и атомарность")
@allure.severity(allure.severity_level.NORMAL)
class TestStateSchema:
    @allure.title("Валидный state сохраняется и читается без изменений")
    def test_round_trip(self, tmp_path):
        with allure.step("Создать и сохранить state"):
            state = _new_state()
            state_mod.save_state(tmp_path, state)
        with allure.step("Прочитать и сравнить ключевые поля"):
            loaded = state_mod.load_state(tmp_path)
        assert loaded["workflow_id"] == state["workflow_id"]
        assert loaded["phase"] == "initialized"
        assert loaded["input"]["revision"] == 1

    @allure.title("workflow_id детерминирован и не принимает head/patch")
    def test_workflow_id_deterministic(self):
        first = state_mod.workflow_id_for(C.PILOT_ID, C.APP_REPO_KEY,
                                          C.APP_BASE_SHA)
        second = state_mod.workflow_id_for(C.PILOT_ID, C.APP_REPO_KEY,
                                           C.APP_BASE_SHA)
        other = state_mod.workflow_id_for(C.PILOT_ID, C.APP_REPO_KEY,
                                          C.APP_BASE_SHA_2)
        assert first == second != other
        assert first.startswith("wf-")

    @allure.title("Нормализация repo: регистр path сохраняется")
    def test_repo_key_normalization(self):
        https = state_mod.normalize_repo_key(C.APP_REPO)
        ssh = state_mod.normalize_repo_key(C.APP_REPO_SSH)
        assert https == ssh == C.APP_REPO_KEY
        assert "Org/Unit-App" in https

    @allure.title("Повреждённый JSON отклоняется без перезаписи файла")
    def test_corrupt_state_rejected(self, tmp_path):
        path = state_mod.state_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not-json", encoding="utf-8")
        before = path.read_bytes()
        with pytest.raises(state_mod.WorkflowStateCorruptError):
            state_mod.load_state(tmp_path)
        assert path.read_bytes() == before

    @allure.title("Неподдерживаемая версия схемы отклоняется")
    def test_unsupported_schema(self, tmp_path):
        state = _new_state()
        state["workflow_schema_version"] = 99
        path = state_mod.state_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
        with pytest.raises(state_mod.WorkflowSchemaError):
            state_mod.load_state(tmp_path)

    @allure.title("app_head kind=patch с git_sha отклоняется")
    def test_bad_head_kind(self, tmp_path):
        state = _new_state()
        state["input"]["revision_data"]["app_head"] = {
            "kind": "patch", "sha256": "a" * 64, "git_sha": "b" * 40}
        path = state_mod.state_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
        with pytest.raises(state_mod.WorkflowSchemaError):
            state_mod.load_state(tmp_path)

    @allure.title("Пропуск фазы в записанном state отклоняется")
    def test_phase_skip_rejected(self, tmp_path):
        state = _new_state()
        state["phase"] = "implementation_ready"
        path = state_mod.state_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
        with pytest.raises(state_mod.WorkflowSchemaError):
            state_mod.load_state(tmp_path)

    @allure.title("phase=published без подтверждённых публикаций отклоняется")
    def test_false_published_rejected(self, tmp_path):
        state = _new_state()
        state["phase"] = "published"
        path = state_mod.state_path(tmp_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state), encoding="utf-8")
        with pytest.raises(state_mod.WorkflowSchemaError):
            state_mod.load_state(tmp_path)

    @allure.title("Обрезанная запись state даёт corrupt, не молчаливый новый")
    def test_truncated_state_rejected(self, tmp_path):
        state = _new_state()
        path = state_mod.save_state(tmp_path, state)
        payload = path.read_bytes()
        path.write_bytes(payload[: len(payload) // 2])
        with pytest.raises(state_mod.WorkflowStateCorruptError):
            state_mod.load_state(tmp_path)

    @allure.title("Запись валидирует state перед сохранением")
    def test_save_validates(self, tmp_path):
        state = _new_state()
        state["phase"] = "published"
        with pytest.raises(state_mod.WorkflowSchemaError):
            state_mod.save_state(tmp_path, state)
        assert not state_mod.state_path(tmp_path).exists()


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("Index: единый журнал lineage")
@allure.severity(allure.severity_level.NORMAL)
class TestIndex:
    @allure.title("Ключ index — repo+pilot; register/find работают")
    def test_register_find(self, tmp_path):
        index = index_mod.new_index()
        index_mod.register(index, C.APP_REPO_KEY, C.PILOT_ID,
                           "wf-" + "1" * 16, C.APP_BASE_SHA)
        index_mod.save_index(tmp_path, index)
        loaded = index_mod.load_index(tmp_path)
        entry = index_mod.find_entry(loaded, C.APP_REPO_KEY, C.PILOT_ID)
        assert entry["base_sha"] == C.APP_BASE_SHA
        assert index_mod.find_entry(
            loaded, C.APP_REPO_KEY, C.OTHER_PILOT_ID) is None
        assert index_mod.find_entry(
            loaded, "other.repo/x", C.PILOT_ID) is None

    @allure.title("Повреждённый index отклоняется без перезаписи")
    def test_corrupt_index(self, tmp_path):
        path = index_mod.index_path(tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        path.write_text("{bad", encoding="utf-8")
        with pytest.raises(state_mod.WorkflowStateCorruptError):
            index_mod.load_index(tmp_path)
        assert path.read_text() == "{bad"

    @allure.title("Чужая схема index отклоняется")
    def test_index_schema(self, tmp_path):
        path = index_mod.index_path(tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"index_schema_version": 42,
                                    "entries": {}}), encoding="utf-8")
        with pytest.raises(state_mod.WorkflowSchemaError):
            index_mod.load_index(tmp_path)


@allure.epic("Инфраструктура")
@allure.feature("Workflow-оркестратор")
@allure.story("Ревизии и каскад stale")
@allure.severity(allure.severity_level.NORMAL)
class TestRevisionCascade:
    def _accepted(self, state, kind):
        record = {"artifact": kind, "actor": "human",
                  "artifact_digest": "ab" * 32,
                  "document": {"path": "d", "sha256": "cd" * 32}}
        if kind == "scenarios":
            record["scenario_ids"] = list(C.SCENARIO_IDS)
        if kind == "review":
            record["decision"] = "approved"
        state_mod.bind_artifact(state, kind, record)

    @allure.title("Новый app_head инвалидирует цепочку зависимостей")
    def test_head_change_cascades(self):
        state = _new_state()
        for kind in ("context", "scenarios", "review"):
            self._accepted(state, kind)
        changed, affected = state_mod.apply_revision(
            state, _revision_data(
                app_head={"kind": "patch", "sha256": C.APP_PATCH_SHA256_2,
                          "git_sha": None}),
            "new patch")
        assert "app_head" in changed
        assert set(affected) == {"context", "scenarios", "review"}
        assert state["input"]["revision"] == 2
        assert state_mod.implied_phase(state) == "initialized"

    @allure.title("Неизменные входы сохраняют принятые артефакты")
    def test_unchanged_inputs_keep_artifacts(self):
        state = _new_state()
        for kind in ("context", "scenarios", "review", "implementation"):
            self._accepted(state, kind)
        changed, affected = state_mod.apply_revision(
            state, _revision_data(
                tests_repo={"commit": C.TESTS_COMMIT_2, "dirty": True,
                            "snapshot_sha256": "9" * 64}),
            "new tests snapshot")
        assert changed == ["tests_repo"]
        assert affected == ["implementation"]
        assert state_mod.artifact_fresh(state, "review")
        assert state_mod.implied_phase(state) == "approved"

    @allure.title("PR-публикации ревизионные: verified -> blocked при T8")
    def test_pr_entries_revisioned(self):
        state = _new_state()
        for role, entry in state["publications"]["pr"].items():
            entry["status"] = "verified"
        state_mod.apply_revision(
            state, _revision_data(
                app_head={"kind": "patch", "sha256": C.APP_PATCH_SHA256_2,
                          "git_sha": None}),
            "new patch")
        for entry in state["publications"]["pr"].values():
            assert entry["status"] == "blocked"

    @allure.title("Незавершённые intents перечисляются для наследования")
    def test_unfinished_intents(self):
        state = _new_state()
        intent = state_mod.new_intent(state, "pr.create", {"repo": "app"})
        intent["status"] = "dispatched"
        done = state_mod.new_intent(state, "testops.upload",
                                    {"execution": "run-x"})
        state_mod.set_intent(done, "completed", {"exit_code": 0})
        open_ids = [i["intent_id"]
                    for i in state_mod.unfinished_intents(state)]
        assert open_ids == [intent["intent_id"]]
