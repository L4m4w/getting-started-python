import argparse
from datetime import datetime
import json
from pathlib import Path
import subprocess
from unittest.mock import Mock

import allure
import pytest

from tools import harness
from test_data.consts.harness import (
    API_CONTRACT_SOURCES, API_SELECTION, APP_BASE_SHA, APP_PATCH_SHA256,
    CONTAINER_ID, DAEMON_DOWN_STDERR, DOCKER_INSPECT, ENV_FILENAME,
    EXPECTED_RUN_COUNT, EXPECTED_SUMMARY, FAILED_EXIT_CODE, GATEWAY_CONTAINER,
    GATEWAY_IMAGE_ID, GATEWAY_IMAGE_MISMATCH, IMAGE_ID_FULL, IMAGE_TAG,
    INVALID_CONTAINER_REF, INVALID_SHA, JUNIT_INVALID, JUNIT_MIXED,
    LAUNCH_FAILURE_CASES, MISSING_CONTRACT_SOURCE, NO_SUCH_CONTAINER_STDERR,
    PRIVATE_ENV_KEY, PRIVATE_PARAMETER_SELECTION, PRIVATE_VALUE,
    REPOSITORY_STATE, SUCCESS_EXIT_CODE, UNIT_SELECTION, UNSAFE_BROWSER_VERSION,
)


@pytest.fixture
def evidence_harness(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    monkeypatch.setattr(harness, "_repository_state", lambda: dict(REPOSITORY_STATE))
    return argparse.Namespace(scope="group", browser=None, bversion=None,
                              app_base_sha=None, app_patch_sha256=None,
                              gateway_image_id=None, gateway_container=None)


@pytest.fixture
def api_harness(tmp_path, monkeypatch):
    """Поддельный корень с контрактными исходниками API и без git/docker."""
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    monkeypatch.setattr(harness, "_repository_state", lambda: dict(REPOSITORY_STATE))
    for relpath, content in API_CONTRACT_SOURCES.items():
        path = tmp_path / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(harness, "API_SOURCE_FILES",
                        (*API_CONTRACT_SOURCES, MISSING_CONTRACT_SOURCE))

    def fake_git(args):
        if args[0] == "hash-object":
            return Mock(returncode=0, stdout="c" * 40 + "\n")
        return Mock(returncode=0, stdout="")

    monkeypatch.setattr(harness, "_git", fake_git)
    return argparse.Namespace(scope="group", browser=None, bversion=None,
                              app_base_sha=None, app_patch_sha256=None,
                              gateway_image_id=None, gateway_container=None)


@allure.epic("Инфраструктура")
@allure.feature("Локальный harness")
@allure.story("Доказательства выполнения")
@allure.severity(allure.severity_level.NORMAL)
class TestRunEvidence:

    @allure.title("Падение тестов сохраняет exit code и отдельные категории JUnit")
    def test_failure_retains_summary_without_private_content(self, evidence_harness, tmp_path, monkeypatch):
        with allure.step("Подменить выполнение падающим прогоном с JUnit"):
            def execute(args):
                output = next(item.split("=", 1)[1] for item in args if item.startswith("--junitxml="))
                Path(output).write_text(JUNIT_MIXED, encoding="utf-8")
                return FAILED_EXIT_CODE
            monkeypatch.setattr(harness, "command", execute)
            monkeypatch.setenv(PRIVATE_ENV_KEY, PRIVATE_VALUE)
            evidence_harness.bversion = UNSAFE_BROWSER_VERSION

        with allure.step("Запустить harness и прочитать манифест"):
            result = harness.run_with_evidence(PRIVATE_PARAMETER_SELECTION, evidence_harness)
            file = next(tmp_path.glob("artifacts/harness/run-*/manifest.json"))
            content = file.read_text(encoding="utf-8")
            manifest = json.loads(content)

        with allure.step("Проверить результат, версии, время и отсутствие приватных данных"):
            assert result == manifest["exit_code"] == FAILED_EXIT_CODE
            assert manifest["junit_summary"] == EXPECTED_SUMMARY
            assert manifest["repository"] == REPOSITORY_STATE
            assert manifest["status"] == "completed"
            assert datetime.fromisoformat(manifest["finished_at"]) >= datetime.fromisoformat(manifest["started_at"])
            assert PRIVATE_VALUE not in content
            assert PRIVATE_ENV_KEY not in content
            assert manifest["selection"]["parameter_ids_omitted"]

    @pytest.mark.parametrize("junit", (None, JUNIT_INVALID))
    @allure.title("Отсутствующий или повреждённый JUnit не превращается в успешную сводку")
    def test_unavailable_junit_is_explicit(self, evidence_harness, tmp_path, monkeypatch, junit):
        with allure.step("Подменить прогон без пригодного JUnit"):
            def execute(args):
                if junit is not None:
                    output = next(item.split("=", 1)[1] for item in args if item.startswith("--junitxml="))
                    Path(output).write_text(junit, encoding="utf-8")
                return FAILED_EXIT_CODE
            monkeypatch.setattr(harness, "command", execute)

        with allure.step("Проверить сохранённую ошибку и недоступную сводку"):
            assert harness.run_with_evidence(UNIT_SELECTION, evidence_harness) == FAILED_EXIT_CODE
            manifest = json.loads(next(tmp_path.glob("artifacts/harness/run-*/manifest.json")).read_text())
            assert manifest["junit_summary"] is None
            assert manifest["finished_at"] is not None

    @pytest.mark.parametrize("failure, expected_code, expected_status", LAUNCH_FAILURE_CASES)
    @allure.title("Ошибка запуска и прерывание оставляют завершённый манифест")
    def test_launch_failure_is_retained(self, evidence_harness, tmp_path, monkeypatch,
                                       failure, expected_code, expected_status):
        with allure.step("Подменить выполнение ошибкой или прерыванием"):
            monkeypatch.setattr(harness, "command", Mock(side_effect=failure))

        with allure.step("Проверить код завершения и сохранённое состояние"):
            assert harness.run_with_evidence(UNIT_SELECTION, evidence_harness) == expected_code
            manifest = json.loads(next(tmp_path.glob("artifacts/harness/run-*/manifest.json")).read_text())
            assert manifest["status"] == expected_status
            assert manifest["exit_code"] == expected_code
            assert manifest["finished_at"] is not None
            assert manifest["junit_summary"] is None

    @allure.title("Новый прогон не наследует JUnit предыдущего выполнения")
    def test_runs_are_isolated(self, evidence_harness, tmp_path, monkeypatch):
        with allure.step("Выполнить первый прогон и сохранить его результаты"):
            def execute(args):
                output = next(item.split("=", 1)[1] for item in args if item.startswith("--junitxml="))
                Path(output).write_text(JUNIT_MIXED, encoding="utf-8")
                return FAILED_EXIT_CODE
            monkeypatch.setattr(harness, "command", execute)
            harness.run_with_evidence(UNIT_SELECTION, evidence_harness)

        with allure.step("Выполнить следующий прогон без нового JUnit"):
            monkeypatch.setattr(harness, "command", Mock(return_value=SUCCESS_EXIT_CODE))
            harness.run_with_evidence(UNIT_SELECTION, evidence_harness)
            manifests = [json.loads(path.read_text())
                         for path in tmp_path.glob("artifacts/harness/run-*/manifest.json")]

        with allure.step("Проверить разные ID и отсутствие унаследованной сводки"):
            assert len({item["run_id"] for item in manifests}) == len(manifests) == EXPECTED_RUN_COUNT
            assert any(item["junit_summary"] == EXPECTED_SUMMARY for item in manifests)
            assert any(item["exit_code"] == SUCCESS_EXIT_CODE and item["junit_summary"] is None
                       for item in manifests)


@allure.epic("Инфраструктура")
@allure.feature("Локальный harness")
@allure.story("Идентичность исходников API-прогона")
@allure.severity(allure.severity_level.NORMAL)
class TestApiSourceIdentity:

    @allure.title("API-прогон фиксирует хеши и копии контрактных исходников до pytest")
    def test_api_run_records_source_identity_and_copies(self, api_harness, tmp_path, monkeypatch):
        with allure.step("Подменить выполнение успешным прогоном"):
            monkeypatch.setattr(harness, "command", Mock(return_value=SUCCESS_EXIT_CODE))

        with allure.step("Запустить API-выбор и прочитать манифест"):
            assert harness.run_with_evidence(API_SELECTION, api_harness) == SUCCESS_EXIT_CODE
            evidence = next(tmp_path.glob("artifacts/harness/run-*"))
            content = (evidence / "manifest.json").read_text(encoding="utf-8")
            manifest = json.loads(content)

        with allure.step("Проверить контракт, отпечатки, копии и отсутствие изменений"):
            identity = manifest["source_identity"]
            assert identity["contract_version"] == harness.API_CONTRACT_VERSION
            assert identity["missing"] == [MISSING_CONTRACT_SOURCE]
            assert sorted(identity["copies"]) == sorted(API_CONTRACT_SOURCES)
            fingerprints = {item["path"]: item for item in identity["files"]}
            assert set(fingerprints) == set(API_CONTRACT_SOURCES) | {MISSING_CONTRACT_SOURCE}
            present = fingerprints["tests/api/test_category_update.py"]
            assert len(present["sha256"]) == 64
            assert present["git_blob"] == "c" * 40
            assert present["tracked"] is True
            absent = fingerprints[MISSING_CONTRACT_SOURCE]
            assert absent == {"path": MISSING_CONTRACT_SOURCE, "sha256": None,
                              "git_blob": None, "tracked": None}
            assert identity["changed_during_run"] == []
            assert identity["rechecked_at"] is not None
            assert manifest["artifacts"]["sources"] == "sources"

        with allure.step("Проверить физические копии исходников в evidence"):
            for relpath, expected in API_CONTRACT_SOURCES.items():
                assert (evidence / "sources" / relpath).read_text(encoding="utf-8") == expected

    @allure.title("Изменение контрактного файла во время прогона отражается явно")
    def test_change_during_run_is_explicit(self, api_harness, tmp_path, monkeypatch):
        with allure.step("Подменить прогон, меняющий исходник во время выполнения"):
            def execute(args):
                (tmp_path / "tests/api/test_category_update.py").write_text(
                    "def test_case():\n    assert False\n", encoding="utf-8")
                (tmp_path / MISSING_CONTRACT_SOURCE).write_text("pass\n", encoding="utf-8")
                return SUCCESS_EXIT_CODE
            monkeypatch.setattr(harness, "command", execute)

        with allure.step("Проверить список изменённых во время прогона файлов"):
            harness.run_with_evidence(API_SELECTION, api_harness)
            manifest = json.loads(next(tmp_path.glob("artifacts/harness/run-*/manifest.json")).read_text())
            assert manifest["source_identity"]["changed_during_run"] == [
                "tests/api/test_category_update.py", MISSING_CONTRACT_SOURCE]

    @allure.title("Прогон вне tests/api не создаёт идентичность исходников")
    def test_non_api_scope_has_no_source_identity(self, api_harness, tmp_path, monkeypatch):
        with allure.step("Подменить выполнение и запустить unit-выбор"):
            monkeypatch.setattr(harness, "command", Mock(return_value=SUCCESS_EXIT_CODE))
            harness.run_with_evidence(UNIT_SELECTION, api_harness)
            evidence = next(tmp_path.glob("artifacts/harness/run-*"))
            manifest = json.loads((evidence / "manifest.json").read_text())

        with allure.step("Проверить отсутствие блока идентичности и копий"):
            assert manifest["source_identity"] is None
            assert manifest["artifacts"]["sources"] is None
            assert not (evidence / "sources").exists()

    @allure.title("Файл с секретами не fingerprint'ится и не копируется в evidence")
    def test_env_file_never_captured(self, api_harness, tmp_path, monkeypatch):
        with allure.step("Добавить .env с секретом в подменный контракт"):
            (tmp_path / ENV_FILENAME).write_text(f"KEY={PRIVATE_VALUE}\n", encoding="utf-8")
            monkeypatch.setattr(harness, "API_SOURCE_FILES",
                                (*API_CONTRACT_SOURCES, ENV_FILENAME))
            monkeypatch.setattr(harness, "command", Mock(return_value=SUCCESS_EXIT_CODE))

        with allure.step("Запустить API-прогон и прочитать манифест"):
            harness.run_with_evidence(API_SELECTION, api_harness)
            evidence = next(tmp_path.glob("artifacts/harness/run-*"))
            content = (evidence / "manifest.json").read_text(encoding="utf-8")
            manifest = json.loads(content)

        with allure.step("Проверить отсутствие .env в отпечатках, копиях и тексте"):
            paths = {item["path"] for item in manifest["source_identity"]["files"]}
            assert ENV_FILENAME not in paths | set(manifest["source_identity"]["copies"])
            assert not (evidence / "sources" / ENV_FILENAME).exists()
            assert PRIVATE_VALUE not in content


@allure.epic("Инфраструктура")
@allure.feature("Локальный harness")
@allure.story("Метаданные окружения прогона")
@allure.severity(allure.severity_level.NORMAL)
class TestEnvironmentMetadata:

    @allure.title("Декларация оператора сохраняется отдельно от проверки контейнера")
    def test_declared_environment_without_container(self, api_harness, tmp_path, monkeypatch):
        with allure.step("Передать метаданные без контейнера и подменить прогон"):
            api_harness.app_base_sha = APP_BASE_SHA
            api_harness.app_patch_sha256 = APP_PATCH_SHA256
            api_harness.gateway_image_id = GATEWAY_IMAGE_ID
            monkeypatch.setattr(harness, "command", Mock(return_value=SUCCESS_EXIT_CODE))
            inspect = Mock()
            monkeypatch.setattr(harness, "_container_check", inspect)

        with allure.step("Запустить прогон и прочитать манифест"):
            harness.run_with_evidence(API_SELECTION, api_harness)
            manifest = json.loads(next(tmp_path.glob("artifacts/harness/run-*/manifest.json")).read_text())

        with allure.step("Проверить декларацию и явный отказ проверки без вызова docker"):
            environment = manifest["environment"]
            declared = environment["declared"]
            assert declared["app_base_sha"] == APP_BASE_SHA
            assert declared["app_patch_sha256"] == APP_PATCH_SHA256
            assert declared["gateway_image_id"] == GATEWAY_IMAGE_ID
            assert declared["gateway_container"] is None
            assert declared["source"] == "operator"
            assert declared["captured_at"] is not None
            assert environment["container_check"] == {
                "performed": False, "reason": "container not declared", "checked_at": None}
            inspect.assert_not_called()

    @allure.title("Результат проверки контейнера сохраняется рядом с декларацией")
    def test_container_check_result_is_recorded(self, api_harness, tmp_path, monkeypatch):
        with allure.step("Задать контейнер и подменить его проверку"):
            api_harness.gateway_container = GATEWAY_CONTAINER
            api_harness.gateway_image_id = GATEWAY_IMAGE_ID
            check = {"performed": True, "reason": None, "matches_declared_image": True}
            monkeypatch.setattr(harness, "_container_check", Mock(return_value=check))
            monkeypatch.setattr(harness, "command", Mock(return_value=SUCCESS_EXIT_CODE))

        with allure.step("Запустить прогон и проверить вызов и запись результата"):
            harness.run_with_evidence(API_SELECTION, api_harness)
            manifest = json.loads(next(tmp_path.glob("artifacts/harness/run-*/manifest.json")).read_text())
            harness._container_check.assert_called_once_with(GATEWAY_CONTAINER, GATEWAY_IMAGE_ID)
            assert manifest["environment"]["container_check"] == check
            assert manifest["environment"]["declared"]["gateway_container"] == GATEWAY_CONTAINER

    @allure.title("Без флагов окружения блок environment отсутствует")
    def test_no_environment_flags_gives_null(self, api_harness, tmp_path, monkeypatch):
        with allure.step("Подменить прогон без метаданных окружения"):
            monkeypatch.setattr(harness, "command", Mock(return_value=SUCCESS_EXIT_CODE))
            harness.run_with_evidence(API_SELECTION, api_harness)
            manifest = json.loads(next(tmp_path.glob("artifacts/harness/run-*/manifest.json")).read_text())

        with allure.step("Проверить явное отсутствие блока"):
            assert manifest["environment"] is None

    @allure.title("Inspect сохраняет только дистиллированные поля и сверяет image")
    def test_container_check_distills_inspect(self, monkeypatch):
        with allure.step("Подменить docker inspect ответом с секретным Env"):
            monkeypatch.setattr(harness.subprocess, "run", Mock(
                return_value=Mock(returncode=0,
                                  stdout=json.dumps([DOCKER_INSPECT], default=dict))))

        with allure.step("Выполнить проверку и прочитать результат"):
            check = harness._container_check(GATEWAY_CONTAINER, GATEWAY_IMAGE_ID)

        with allure.step("Проверить поля, совпадение image и отсутствие секретов"):
            assert check["performed"] is True and check["reason"] is None
            assert check["container_id"] == CONTAINER_ID
            assert check["container_name"] == GATEWAY_CONTAINER
            assert check["container_running"] is True
            assert check["image_id"] == IMAGE_ID_FULL
            assert check["image_tag"] == IMAGE_TAG
            assert check["matches_declared_image"] is True
            assert PRIVATE_VALUE not in json.dumps(check)
            assert "Env" not in check

    @allure.title("Короткий ID сравнивается по префиксу; несовпадение видно явно")
    def test_container_check_image_matching(self, monkeypatch):
        with allure.step("Подменить inspect одинаковым ответом"):
            monkeypatch.setattr(harness.subprocess, "run", Mock(
                return_value=Mock(returncode=0,
                                  stdout=json.dumps([DOCKER_INSPECT], default=dict))))

        with allure.step("Проверить префикс, несовпадение и отсутствие декларации"):
            assert harness._container_check(
                GATEWAY_CONTAINER, GATEWAY_IMAGE_MISMATCH)["matches_declared_image"] is False
            assert harness._container_check(
                GATEWAY_CONTAINER, None)["matches_declared_image"] is None
            assert harness._container_check(
                GATEWAY_CONTAINER, IMAGE_ID_FULL)["matches_declared_image"] is True

    @allure.title("Недоступный docker, отсутствие контейнера и мусор — performed=false")
    @pytest.mark.parametrize("outcome, reason", (
        (OSError(), "docker unavailable"),
        (subprocess.TimeoutExpired("docker", 10), "docker unavailable"),
        (Mock(returncode=1, stderr=NO_SUCH_CONTAINER_STDERR), "container not found"),
        (Mock(returncode=1, stderr=DAEMON_DOWN_STDERR), "docker daemon unavailable"),
        (Mock(returncode=1, stderr="other"), "inspect failed"),
        (Mock(returncode=0, stdout="not-json"), "inspect output unreadable"),
        (Mock(returncode=0, stdout="[]"), "inspect output unreadable"),
    ))
    def test_container_check_failures_are_explicit(self, monkeypatch, outcome, reason):
        with allure.step("Подменить результат вызова docker"):
            run = Mock(side_effect=outcome) if isinstance(outcome, BaseException) \
                else Mock(return_value=outcome)
            monkeypatch.setattr(harness.subprocess, "run", run)

        with allure.step("Проверить явную причину без проверенных полей"):
            check = harness._container_check(GATEWAY_CONTAINER, GATEWAY_IMAGE_ID)
            assert check["performed"] is False
            assert check["reason"] == reason
            assert check["container_running"] is None
            assert check["image_id"] is None
            assert check["matches_declared_image"] is None
            assert check["checked_at"] is not None

    @allure.title("Невалидные значения метаданных отклоняются разбором аргументов")
    @pytest.mark.parametrize("validator, value", (
        (harness._git_sha, INVALID_SHA),
        (harness._sha256_hex, INVALID_SHA),
        (harness._image_id, "not!hex"),
        (harness._container_ref, INVALID_CONTAINER_REF),
    ))
    def test_invalid_metadata_rejected(self, validator, value):
        with allure.step("Проверить отказ валидатора на недопустимое значение"):
            with pytest.raises(argparse.ArgumentTypeError):
                validator(value)

    @allure.title("Валидные SHA и image ID нормализуются к нижнему регистру")
    def test_metadata_normalization(self):
        with allure.step("Проверить нормализацию hex-значений"):
            assert harness._git_sha("A" * 40) == "a" * 40
            assert harness._sha256_hex("D" * 64) == "d" * 64
            assert harness._image_id("SHA256:" + "F" * 64) == "sha256:" + "f" * 64
            assert harness._container_ref(GATEWAY_CONTAINER) == GATEWAY_CONTAINER
