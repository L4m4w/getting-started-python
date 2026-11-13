import argparse
from datetime import datetime
import json
from pathlib import Path
from unittest.mock import Mock

import allure
import pytest

from tools import harness
from test_data.consts.harness import (
    EXPECTED_RUN_COUNT, EXPECTED_SUMMARY, FAILED_EXIT_CODE, JUNIT_INVALID,
    JUNIT_MIXED, LAUNCH_FAILURE_CASES, PRIVATE_ENV_KEY, PRIVATE_PARAMETER_SELECTION,
    PRIVATE_VALUE, REPOSITORY_STATE, SUCCESS_EXIT_CODE, UNIT_SELECTION,
    UNSAFE_BROWSER_VERSION,
)


@pytest.fixture
def evidence_harness(tmp_path, monkeypatch):
    monkeypatch.setattr(harness, "ROOT", tmp_path)
    monkeypatch.setattr(harness, "_repository_state", lambda: dict(REPOSITORY_STATE))
    return argparse.Namespace(scope="group", browser=None, bversion=None)


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
