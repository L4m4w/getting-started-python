import json
from pathlib import Path
from unittest.mock import Mock

import allure
import pytest

from tools import testops
from infrastructure.reporting.testops import client, lifecycle
from test_data.consts.testops import (
    ALLURECTL_PATH, BLOCKED_EXIT, BOUND_IDS, ENDPOINT, EXECUTION_ID,
    FAILED_CODE, LAUNCH_ID, LAUNCH_NAME, LAUNCH_URL, PROJECT_ID,
    SUCCESS_CODE, TOKEN_ENV, UNKNOWN_EXIT, UNKNOWN_SCENARIO,
)


def _result(scenario_id, status="passed", uuid=None):
    signature = testops._scenario_index()[scenario_id]
    return {"uuid": uuid or f"uuid-{scenario_id}", "name": "unit title",
            "status": status, "fullName": signature["full_name"],
            "testCaseId": "a" * 32, "historyId": "b" * 32,
            "parameters": [{"name": signature["param"],
                            "value": repr(signature["value"])}],
            "labels": [{"name": "severity", "value": "critical"}]}


def _results_dir(tmp_path, scenario_ids, extra=None):
    directory = tmp_path / "harness" / EXECUTION_ID / "allure-results"
    directory.mkdir(parents=True)
    for index, scenario_id in enumerate(scenario_ids):
        data = _result(scenario_id, uuid=f"uuid-{index}-{scenario_id}")
        name = f"{index:08d}-aaaa-4aaa-8aaa-aaaaaaaaaaaa-result.json"
        (directory / name).write_text(json.dumps(data), encoding="utf-8")
    (directory / "unit-attachment.json").write_text("{}", encoding="utf-8")
    if extra is not None:
        (directory / "ffffffff-0000-4000-8000-0000000000ff-result.json"
         ).write_text(json.dumps(extra), encoding="utf-8")
    return directory


def _state(state_dir):
    return json.loads((Path(state_dir) / "state.json").read_text())


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Изолированный state/env: все вызовы allurectl и токен подменены."""
    monkeypatch.setattr(testops, "STATE_PARENT", tmp_path / "testops")
    monkeypatch.setattr(testops.client, "locate", lambda explicit=None: ALLURECTL_PATH)
    monkeypatch.setenv("ALLURE_TOKEN", TOKEN_ENV)
    monkeypatch.delenv("ALLURE_ENDPOINT", raising=False)
    monkeypatch.delenv("ALLURE_PROJECT_ID", raising=False)
    options = Mock(endpoint=ENDPOINT, project_id=PROJECT_ID,
                   allurectl=ALLURECTL_PATH, results=None, execution=EXECUTION_ID,
                   online=True, execute=True, retry=False, mode="bind",
                   launch_name=LAUNCH_NAME, launch_id=None, timeout=60, transport="allurectl")
    return options


def _options(env, **overrides):
    options = Mock(**{field: getattr(env, field)
                      for field in ("endpoint", "project_id", "allurectl",
                                    "results", "execution", "online", "execute",
                                    "retry", "mode", "launch_name", "launch_id",
                                    "timeout", "transport")})
    for key, value in overrides.items():
        setattr(options, key, value)
    return options


def _parser():
    def fail(message):
        raise SystemExit(f"parser: {message}")
    return Mock(error=fail)


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("План и соответствие сценариев")
@allure.severity(allure.severity_level.NORMAL)
class TestScenarioPlan:

    @allure.title("Шесть параметров двух функций распознаются как шесть сценариев")
    def test_plan_maps_six_parameters_to_six_scenarios(self, env, tmp_path):
        with allure.step("Подготовить шесть результатов в каталоге прогона"):
            directory = _results_dir(tmp_path, sorted(BOUND_IDS))
            options = _options(env, results=str(directory))
        with allure.step("Выполнить plan и прочитать состояние"):
            code = testops.cmd_plan(options, _parser())
            state = _state(tmp_path / "testops" / EXECUTION_ID)
        with allure.step("Проверить полное соответствие без дублей"):
            assert code == SUCCESS_CODE
            assert sorted(state["scenarios"]) == sorted(BOUND_IDS)
            assert state["unmapped"] == []
            assert all(entry["binding"] == "unresolved"
                       for entry in state["scenarios"].values())
            assert state["upload"]["status"] == "pending"

    @allure.title("Незнакомое значение параметра помечается unmapped и блокирует пакет")
    def test_unmapped_result_is_explicit_and_blocks_package(self, env, tmp_path):
        with allure.step("Добавить результат с неизвестным fullName"):
            foreign = _result("CAT-UPD-VAL-001")
            foreign["fullName"] = "tests.api.other#test_other"
            directory = _results_dir(tmp_path, sorted(BOUND_IDS), extra=foreign)
            options = _options(env, results=str(directory))
        with allure.step("Запланировать и попытаться собрать пакет"):
            code = testops.cmd_plan(options, _parser())
            package_code = testops.cmd_package(_options(env, mode="isolate"), _parser())
            state = _state(tmp_path / "testops" / EXECUTION_ID)
        with allure.step("Проверить предупреждение и блок пакета"):
            assert code == SUCCESS_CODE
            assert len(state["unmapped"]) == 1
            assert package_code == BLOCKED_EXIT

    @allure.title("Повторное планирование сохраняет привязки и не создаёт сущностей")
    def test_replan_preserves_bindings(self, env, tmp_path):
        with allure.step("Запланировать, привязать и запланировать повторно"):
            directory = _results_dir(tmp_path, sorted(BOUND_IDS))
            options = _options(env, results=str(directory))
            testops.cmd_plan(options, _parser())
            testops.cmd_assign(_options(env, bindings=["CAT-UPD-VAL-001=9001"]), _parser())
            testops.cmd_plan(options, _parser())
            state = _state(tmp_path / "testops" / EXECUTION_ID)
        with allure.step("Проверить сохранность привязки и отсутствие побочных полей"):
            assert state["scenarios"]["CAT-UPD-VAL-001"]["testops_id"] == 9001
            assert state["scenarios"]["CAT-UPD-VAL-001"]["binding"] == "bound"
            assert state["package"] is None and state["launch"] is None

    @allure.title("assign отклоняет чужой сценарий и дублирующий ID")
    def test_assign_rejects_unknown_scenario_and_duplicate_id(self, env, tmp_path):
        with allure.step("Запланировать и выдать конфликтующие привязки"):
            directory = _results_dir(tmp_path, sorted(BOUND_IDS))
            testops.cmd_plan(_options(env, results=str(directory)), _parser())
            unknown = testops.cmd_assign(
                _options(env, bindings=[f"{UNKNOWN_SCENARIO}=1"]), _parser())
            testops.cmd_assign(_options(env, bindings=["CAT-UPD-VAL-001=42"]), _parser())
            duplicate = testops.cmd_assign(
                _options(env, bindings=["CAT-UPD-VAL-002=42"]), _parser())
        with allure.step("Проверить блокировку обоих присваиваний"):
            assert unknown == duplicate == BLOCKED_EXIT


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Пакет загрузки")
@allure.severity(allure.severity_level.NORMAL)
class TestUploadPackage:

    def _plan(self, env, tmp_path):
        directory = _results_dir(tmp_path, sorted(BOUND_IDS))
        testops.cmd_plan(_options(env, results=str(directory)), _parser())
        return directory

    @allure.title("bind-пакет вставляет ALLURE_ID и сценарную сигнатуру, источник не меняется")
    def test_bind_package_injects_ids_and_keeps_source(self, env, tmp_path):
        with allure.step("Запланировать и привязать шесть кейсов"):
            source = self._plan(env, tmp_path)
            bindings = [f"{key}={value}" for key, value in BOUND_IDS.items()]
            testops.cmd_assign(_options(env, bindings=bindings), _parser())
            before = {p.name: p.read_bytes() for p in source.iterdir()}
        with allure.step("Собрать bind-пакет"):
            code = testops.cmd_package(_options(env, mode="bind"), _parser())
            packaged = tmp_path / "testops" / EXECUTION_ID / "upload-results"
            items = sorted(packaged.glob("*-result.json"))
        with allure.step("Проверить шесть различных привязанных результатов"):
            assert code == SUCCESS_CODE
            assert len(items) == len(BOUND_IDS)
            data = [json.loads(p.read_text()) for p in items]
            assert len({item["testCaseId"] for item in data}) == len(BOUND_IDS)
            for item in data:
                scenario_id = item["name"].split(":", 1)[0]
                assert item["fullName"].endswith(f"[{scenario_id}]")
                bound = [label["value"] for label in item["labels"]
                         if label["name"] == "ALLURE_ID"]
                assert bound == [str(BOUND_IDS[scenario_id])]
            assert {p.name: p.read_bytes() for p in source.iterdir()} == before

    @allure.title("isolate-пакет разводит сигнатуры без ALLURE_ID и bind без ID блокируется")
    def test_isolate_package_distinct_signatures(self, env, tmp_path):
        with allure.step("Запланировать без привязок и проверить блок bind"):
            self._plan(env, tmp_path)
            bind = testops.cmd_package(_options(env, mode="bind"), _parser())
        with allure.step("Собрать isolate-пакет"):
            code = testops.cmd_package(_options(env, mode="isolate"), _parser())
            packaged = tmp_path / "testops" / EXECUTION_ID / "upload-results"
            data = [json.loads(p.read_text())
                    for p in packaged.glob("*-result.json")]
        with allure.step("Проверить шесть уникальных testCaseId без ID-меток"):
            assert bind == BLOCKED_EXIT
            assert code == SUCCESS_CODE
            assert len(data) == len(BOUND_IDS)
            assert len({item["testCaseId"] for item in data}) == len(BOUND_IDS)
            assert len({item["fullName"] for item in data}) == len(BOUND_IDS)
            assert all("ALLURE_ID" not in {l["name"] for l in item["labels"]}
                       for item in data)
            assert {item["name"].split(":", 1)[0] for item in data} == set(BOUND_IDS)


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Загрузка и повторная обработка")
@allure.severity(allure.severity_level.NORMAL)
class TestUploadLifecycle:

    def _packaged(self, env, tmp_path, monkeypatch):
        directory = _results_dir(tmp_path, sorted(BOUND_IDS))
        testops.cmd_plan(_options(env, results=str(directory)), _parser())
        testops.cmd_package(_options(env, mode="isolate"), _parser())
        return tmp_path / "testops" / EXECUTION_ID

    @allure.title("Без --execute и без токена upload не вызывает внешний процесс")
    def test_upload_requires_execute_and_token(self, env, tmp_path, monkeypatch):
        with allure.step("Подготовить пакет и подменить вызов счётчиком"):
            self._packaged(env, tmp_path, monkeypatch)
            calls = []
            monkeypatch.setattr(client, "run", lambda *a, **k: calls.append(a))
            monkeypatch.delenv("ALLURE_TOKEN")
        with allure.step("Вызвать upload без --execute и с --execute без токена"):
            denied = testops.cmd_upload(_options(env, execute=False), _parser())
            blocked = testops.cmd_upload(_options(env, execute=True), _parser())
        with allure.step("Проверить блокировки и отсутствие вызовов"):
            assert denied == blocked == BLOCKED_EXIT
            assert calls == []

    @allure.title("Успешный upload сохраняет launch и запрещает повторную отправку")
    def test_successful_upload_records_launch_and_blocks_repeat(
            self, env, tmp_path, monkeypatch):
        with allure.step("Подменить create/get успешными ответами"):
            state_dir = self._packaged(env, tmp_path, monkeypatch)
            created = client.CommandResult(0, json.dumps({"id": LAUNCH_ID}), "")
            sent = client.CommandResult(0, "uploaded", "")
            calls = []
            def fake_run(binary, args, token=None, timeout=None):
                calls.append(args)
                return created if "create" in args else sent
            monkeypatch.setattr(client, "run", fake_run)
        with allure.step("Выполнить upload и попытаться повторить"):
            code = testops.cmd_upload(_options(env), _parser())
            repeated = testops.cmd_upload(_options(env), _parser())
            state = _state(state_dir)
        with allure.step("Проверить состояние sent и отсутствие повторного вызова"):
            assert code == SUCCESS_CODE
            assert repeated == BLOCKED_EXIT
            assert state["upload"]["status"] == "sent"
            assert state["launch"] == {"id": LAUNCH_ID, "name": LAUNCH_NAME,
                                       "url": LAUNCH_URL, "created_at": state["launch"]["created_at"]}
            assert len(calls) == 2

    @allure.title("Ненулевой exit create оставляет unknown и блокирует retry")
    def test_nonzero_create_blocks_retry(self, env, tmp_path, monkeypatch):
        with allure.step("Подменить launch create отказом 401"):
            state_dir = self._packaged(env, tmp_path, monkeypatch)
            denied = client.CommandResult(FAILED_CODE, "", "401 unauthorized")
            monkeypatch.setattr(client, "run", lambda *a, **k: denied)
        with allure.step("Выполнить upload и повтор без --retry"):
            code = testops.cmd_upload(_options(env), _parser())
            retry_denied = testops.cmd_upload(_options(env), _parser())
            retry_ok = testops.cmd_upload(_options(env, retry=True), _parser())
            state = _state(state_dir)
        with allure.step("Проверить unknown и запрет слепого повтора"):
            assert code == UNKNOWN_EXIT
            assert retry_denied == retry_ok == BLOCKED_EXIT
            assert state["upload"]["status"] == "unknown"
            assert state["upload"]["attempts"] == 1

    @allure.title("Timeout инструмента даёт unknown и блокирует слепой повтор")
    def test_timeout_marks_unknown_and_blocks_blind_retry(
            self, env, tmp_path, monkeypatch):
        with allure.step("Подменить create успехом, а upload — timeout"):
            state_dir = self._packaged(env, tmp_path, monkeypatch)
            created = client.CommandResult(0, json.dumps({"id": LAUNCH_ID}), "")
            stuck = client.CommandResult(None, "", "", "timeout")
            def fake_run(binary, args, token=None, timeout=None):
                return created if "create" in args else stuck
            monkeypatch.setattr(client, "run", fake_run)
        with allure.step("Выполнить upload и попытаться повторить с --retry"):
            code = testops.cmd_upload(_options(env), _parser())
            retry = testops.cmd_upload(_options(env, retry=True), _parser())
            state = _state(state_dir)
        with allure.step("Проверить unknown, сохранённый launch и блок повтора"):
            assert code == UNKNOWN_EXIT
            assert retry == BLOCKED_EXIT
            assert state["upload"]["status"] == "unknown"
            assert state["launch"]["id"] == LAUNCH_ID

    @allure.title("verify без доказательства набора результатов сохраняет unknown")
    def test_verify_keeps_unknown_without_result_evidence(self, env, tmp_path, monkeypatch):
        with allure.step("Получить unknown после timeout и подменить launch get"):
            state_dir = self._packaged(env, tmp_path, monkeypatch)
            created = client.CommandResult(0, json.dumps({"id": LAUNCH_ID}), "")
            stuck = client.CommandResult(None, "", "", "timeout")
            calls = []
            def fake_run(binary, args, token=None, timeout=None):
                calls.append(args)
                if "get" in args:
                    return client.CommandResult(0, json.dumps({"id": LAUNCH_ID}), "")
                return created if "create" in args else stuck
            monkeypatch.setattr(client, "run", fake_run)
            testops.cmd_upload(_options(env), _parser())
        with allure.step("Выполнить verify без --online и с ним"):
            denied = testops.cmd_verify(_options(env, online=False), _parser())
            code = testops.cmd_verify(_options(env, online=True), _parser())
            state = _state(state_dir)
        with allure.step("Проверить сохранение unknown"):
            assert denied == BLOCKED_EXIT
            assert code == UNKNOWN_EXIT
            assert state["upload"]["status"] == "unknown"
            assert state["launch"]["id"] == LAUNCH_ID


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Разрешение привязок")
@allure.severity(allure.severity_level.NORMAL)
class TestCaseResolution:

    def _planned(self, env, tmp_path, monkeypatch):
        directory = _results_dir(tmp_path, sorted(BOUND_IDS))
        testops.cmd_plan(_options(env, results=str(directory)), _parser())
        return tmp_path / "testops" / EXECUTION_ID

    @allure.title("Уникальные совпадения привязывают все шесть сценариев")
    def test_resolve_binds_unique_candidates(self, env, tmp_path, monkeypatch):
        with allure.step("Подменить список кейсов шестью уникальными именами"):
            state_dir = self._planned(env, tmp_path, monkeypatch)
            cases = [{"id": value, "name": f"{key}: кейс"}
                     for key, value in BOUND_IDS.items()]
            monkeypatch.setattr(
                client, "run",
                lambda *a, **k: client.CommandResult(0, json.dumps(cases), ""))
        with allure.step("Выполнить resolve --online"):
            code = testops.cmd_resolve(_options(env), _parser())
            state = _state(state_dir)
        with allure.step("Проверить все привязки по имени"):
            assert code == SUCCESS_CODE
            assert {key: entry["testops_id"]
                    for key, entry in state["scenarios"].items()} == BOUND_IDS

    @allure.title("Два кейса с одним маркером дают ambiguous без выбора")
    def test_resolve_marks_ambiguous_duplicates(self, env, tmp_path, monkeypatch):
        with allure.step("Подменить список двойняшкой для первого сценария"):
            state_dir = self._planned(env, tmp_path, monkeypatch)
            cases = [{"id": 11, "name": "CAT-UPD-VAL-001: один"},
                     {"id": 12, "name": "CAT-UPD-VAL-001 копия"}]
            monkeypatch.setattr(
                client, "run",
                lambda *a, **k: client.CommandResult(0, json.dumps(cases), ""))
        with allure.step("Выполнить resolve --online"):
            code = testops.cmd_resolve(_options(env), _parser())
            state = _state(state_dir)
        with allure.step("Проверить ambiguous и незаполненный ID"):
            assert code == BLOCKED_EXIT
            entry = state["scenarios"]["CAT-UPD-VAL-001"]
            assert entry["binding"] == "ambiguous"
            assert entry["testops_id"] is None

    @allure.title("Разбор ответа test-case list устойчив к обёртке content")
    def test_parse_cases_supports_wrapped_payload(self):
        with allure.step("Разобрать обёрнутый и плоский ответы"):
            wrapped = json.dumps({"content": [{"id": 7, "name": "a"}]})
            flat = json.dumps([{"id": "8", "name": "b"}, {"id": "x"}])
        with allure.step("Проверить нормализацию в числовые ID"):
            assert client.parse_cases(wrapped) == [{"id": 7, "name": "a"}]
            assert client.parse_cases(flat) == [{"id": 8, "name": "b"}]


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Интеграция CLI и строгих проверок")
class TestCliIntegrity:

    @allure.title("Изменение source после plan блокирует package")
    def test_changed_source_blocks_package(self, env, tmp_path):
        with allure.step("Запланировать и изменить исходный каталог"):
            directory = _results_dir(tmp_path, sorted(BOUND_IDS))
            testops.cmd_plan(_options(env, results=str(directory)), _parser())
            next(directory.glob("*-result.json")).write_text("{}")
        with allure.step("Проверить отказ без пакета"):
            assert testops.cmd_package(_options(env, mode="isolate"), _parser()) == BLOCKED_EXIT
            assert _state(tmp_path / "testops" / EXECUTION_ID)["package"] is None

    @allure.title("Изменение source или bindings после package блокирует upload до сети")
    @pytest.mark.parametrize("change", ("source", "bindings"))
    def test_stale_package_never_calls_network(self, env, tmp_path, monkeypatch, change):
        with allure.step("Подготовить пакет и изменить один из входов"):
            directory = _results_dir(tmp_path, sorted(BOUND_IDS))
            testops.cmd_plan(_options(env, results=str(directory)), _parser())
            testops.cmd_assign(_options(env, bindings=[f"{k}={v}" for k, v in BOUND_IDS.items()]), _parser())
            testops.cmd_package(_options(env, mode="bind"), _parser())
            if change == "source":
                next(directory.glob("*-result.json")).write_text("{}")
            else:
                state_dir = tmp_path / "testops" / EXECUTION_ID
                state = _state(state_dir)
                state["scenarios"][next(iter(BOUND_IDS))]["testops_id"] = LAUNCH_ID
                testops.state_mod.save_state(state_dir, state)
            calls = []
            monkeypatch.setattr(client, "run", lambda *a, **k: calls.append(a))
        with allure.step("Проверить блокировку до внешнего вызова"):
            assert testops.cmd_upload(_options(env), _parser()) == BLOCKED_EXIT
            assert calls == []

    @allure.title("Повреждённый state блокирует plan без перезаписи")
    def test_corrupt_state_blocks_plan(self, env, tmp_path):
        with allure.step("Создать повреждённое состояние"):
            directory = _results_dir(tmp_path, sorted(BOUND_IDS))
            state_dir = tmp_path / "testops" / EXECUTION_ID
            state_dir.mkdir(parents=True)
            path = state_dir / "state.json"
            path.write_text("{")
        with allure.step("Проверить явный отказ и сохранность файла"):
            assert testops.cmd_plan(_options(env, results=str(directory)), _parser()) == BLOCKED_EXIT
            assert path.read_text() == "{"

    @allure.title("Блокировка CLI охватывает внешний вызов и сохранение")
    def test_upload_holds_execution_lock(self, env, tmp_path, monkeypatch):
        with allure.step("Подготовить пакет и перехватить внешний вызов"):
            directory = _results_dir(tmp_path, sorted(BOUND_IDS))
            testops.cmd_plan(_options(env, results=str(directory)), _parser())
            testops.cmd_package(_options(env, mode="isolate"), _parser())
            state_dir = tmp_path / "testops" / EXECUTION_ID
            def fake_run(binary, args, **kwargs):
                with pytest.raises(lifecycle.LockHeldError):
                    lifecycle.ExecutionLock(state_dir, "second upload").acquire()
                return client.CommandResult(0, json.dumps({"id": LAUNCH_ID}), "")
            monkeypatch.setattr(client, "run", fake_run)
        with allure.step("Выполнить upload под единой блокировкой"):
            assert testops.cmd_upload(_options(env), _parser()) == SUCCESS_CODE
            assert _state(state_dir)["upload"]["status"] == "sent"

    @allure.title("Корневой .env загружается без переопределения exported token")
    @pytest.mark.parametrize("source", ("dotenv", "exported", "missing"))
    def test_project_dotenv(self, tmp_path, monkeypatch, source, capsys):
        with allure.step("Изолировать окружение и корень проекта"):
            monkeypatch.setattr(testops, "ROOT", tmp_path)
            # Enable dotenv only inside this isolated synthetic tmp root.
            # monkeypatch restores the outer safety flag after this test.
            monkeypatch.delenv("PYTHON_DOTENV_DISABLED", raising=False)
            monkeypatch.delenv("ALLURE_TOKEN", raising=False)
            if source != "missing":
                (tmp_path / ".env").write_text(f"ALLURE_TOKEN={TOKEN_ENV}\n")
            if source == "exported":
                monkeypatch.setenv("ALLURE_TOKEN", ALLURECTL_PATH)
        with allure.step("Загрузить конфигурацию и проверить приоритет без вывода"):
            testops.load_environment()
            expected = {"dotenv": TOKEN_ENV, "exported": ALLURECTL_PATH, "missing": None}[source]
            assert testops._token() == expected
            captured = capsys.readouterr()
            assert TOKEN_ENV not in captured.out + captured.err


    @allure.title("Флаг отключения dotenv не загружает даже synthetic tmp .env")
    def test_project_dotenv_disabled(self, tmp_path, monkeypatch, capsys):
        with allure.step("Изолировать root и явно отключить dotenv"):
            monkeypatch.setattr(testops, "ROOT", tmp_path)
            monkeypatch.delenv("ALLURE_TOKEN", raising=False)
            monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
            (tmp_path / ".env").write_text(f"ALLURE_TOKEN={TOKEN_ENV}\n")
        with allure.step("Проверить отказ загрузки без вывода synthetic token"):
            testops.load_environment()
            assert testops._token() is None
            captured = capsys.readouterr()
            assert TOKEN_ENV not in captured.out + captured.err


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("CLI и реальный REST probe с подменённым HTTP")
class TestRestCliIntegration:

    @allure.title("REST verify связывает пакет, HTTP-ответы и полное подтверждение")
    def test_rest_verifies_recorded_package(self, env, tmp_path, monkeypatch):
        with allure.step("Подготовить bind-пакет и записанную отправку"):
            directory = _results_dir(tmp_path, sorted(BOUND_IDS))
            testops.cmd_plan(_options(env, results=str(directory)), _parser())
            testops.cmd_assign(_options(env, bindings=[f"{k}={v}" for k, v in BOUND_IDS.items()]), _parser())
            testops.cmd_package(_options(env, mode="bind"), _parser())
            state_dir = tmp_path / "testops" / EXECUTION_ID
            state = _state(state_dir)
            testops.state_mod.mark_upload_started(state, state["package"]["sha256"])
            testops.state_mod.record_launch(state, LAUNCH_ID, LAUNCH_NAME, LAUNCH_URL)
            testops.state_mod.mark_upload_finished(state, "sent", SUCCESS_CODE)
            testops.state_mod.save_state(state_dir, state)
        with allure.step("Подменить только HTTP, оставив RestProbe и verifier настоящими"):
            from http import HTTPStatus
            from infrastructure.http.client import HttpResponse
            from test_data.consts import testops_rest as tr
            from test_data.consts.testops_verification import RESULT_TITLE
            real_probe = testops.rest.RestProbe
            calls = []
            rows = [tr.result_item(index, name=f"{sid}: {RESULT_TITLE}", test_case_id=case,
                                   launch_id=LAUNCH_ID, project_id=PROJECT_ID)
                    for index, (sid, case) in enumerate(BOUND_IDS.items(), start=1)]
            class Http:
                def request(self, endpoint, method, path, **kwargs):
                    calls.append((method, path))
                    assert endpoint == ENDPOINT
                    if method == "POST":
                        assert path == tr.TOKEN_PATH
                        payload = tr.TOKEN_OK
                    elif path.endswith("/progress"):
                        payload = tr.PROGRESS_READY
                    elif path.endswith("/statistic"):
                        payload = [{"status": "passed", "count": len(rows)}]
                    elif path.startswith("/api/testresult?"):
                        payload = tr.page(0, rows, len(rows), 1, True, size=100)
                    else:
                        assert path == f"/api/launch/{LAUNCH_ID}"
                        payload = dict(tr.LAUNCH, id=LAUNCH_ID, projectId=PROJECT_ID)
                    return HttpResponse(HTTPStatus.OK, json.dumps(payload).encode(), None)
            monkeypatch.setattr(testops.rest, "RestProbe", lambda token: real_probe(token, http=Http()))
            def no_allurectl(*args, **kwargs):
                raise AssertionError("REST verification must not require allurectl")
            monkeypatch.setattr(client, "locate", no_allurectl)
        with allure.step("Подтвердить все шесть сценариев без внешних вызовов"):
            code = testops.cmd_verify(_options(env, transport="rest"), _parser())
            confirmed = _state(state_dir)
            assert code == SUCCESS_CODE
            assert confirmed["upload"]["status"] == "uploaded"
            assert confirmed["upload"]["confirmation"]["method"] == "rest-snapshot"
            assert len(calls) == 6
            assert TOKEN_ENV not in (state_dir / "upload.log").read_text()

    @allure.title("REST verify блокируется до HTTP при изменении пакета")
    def test_rest_blocks_changed_package(self, env, tmp_path, monkeypatch):
        with allure.step("Подготовить пакет и изменить его после сборки"):
            directory = _results_dir(tmp_path, sorted(BOUND_IDS))
            testops.cmd_plan(_options(env, results=str(directory)), _parser())
            testops.cmd_package(_options(env, mode="isolate"), _parser())
            state_dir = tmp_path / "testops" / EXECUTION_ID
            next((state_dir / "upload-results").glob("*-result.json")).write_text("{}")
            calls = []
            monkeypatch.setattr(testops.rest, "RestProbe", lambda token: calls.append(token))
        with allure.step("Проверить отказ до создания probe"):
            assert testops.cmd_verify(_options(env, transport="rest"), _parser()) == BLOCKED_EXIT
            assert calls == []

    @allure.title("resolve не связывает сценарий 001 с кейсом 0010")
    def test_resolve_rejects_numeric_prefix(self, env, tmp_path, monkeypatch):
        with allure.step("Вернуть кейс с более длинным номером"):
            from test_data.consts.testops_verification import SID_LOOKALIKE
            directory = _results_dir(tmp_path, sorted(BOUND_IDS))
            testops.cmd_plan(_options(env, results=str(directory)), _parser())
            monkeypatch.setattr(client, "run", lambda *a, **k: client.CommandResult(
                SUCCESS_CODE, json.dumps([{"id": LAUNCH_ID, "name": SID_LOOKALIKE}]), ""))
        with allure.step("Проверить отсутствие ложной привязки"):
            assert testops.cmd_resolve(_options(env), _parser()) == BLOCKED_EXIT
            assert all(item["testops_id"] is None for item in
                       _state(tmp_path / "testops" / EXECUTION_ID)["scenarios"].values())
