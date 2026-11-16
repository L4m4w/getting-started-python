import argparse
from datetime import datetime
import json
from pathlib import Path
import signal
import subprocess
from unittest.mock import Mock

import allure
import pytest

from tools import java_evidence
from test_data.consts.java_evidence import (
    APP_REPO_STATE, ARGPARSE_EXIT_CODE, EXPECTED_COMMAND, EXPECTED_RUN_COUNT,
    EXPECTED_SUMMARY, FAILED_EXIT_CODE, INVALID_MODULE, INVALID_SELECTOR,
    JAVA_VERSION_LINE, JUNIT_FILENAME, JUNIT_GRADLE, LABEL_BASELINE,
    LAUNCH_FAILURE_CASES, MODULE, PATCH_TEXT, SUCCESS_EXIT_CODE,
    INTERRUPT_EXIT_CODE, INVALID_JUNIT, PROCESS_PID, SECOND_JUNIT_FILENAME,
    TARGET_RELPATH, TARGET_SOURCE, TEST_CLASS, TEST_FILE_RELPATH,
    TEST_SELECTOR_METHOD, TEST_SOURCE, UP_TO_DATE_LOG, WRAPPER_VERSION,
)


def _results_dir(repo):
    return Path(repo) / MODULE / "build" / "test-results" / "test"


def _manifests(tmp_path):
    return [json.loads(path.read_text())
            for path in (tmp_path / "evidence").glob("run-*/manifest.json")]


@pytest.fixture
def java_run(tmp_path, monkeypatch):
    """Поддельный репозиторий приложения и среда без git, Java и Gradle."""
    repo = tmp_path / "app"
    test_file = repo / TEST_FILE_RELPATH
    target_file = repo / TARGET_RELPATH
    for path in (test_file, target_file):
        path.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(TEST_SOURCE, encoding="utf-8")
    target_file.write_text(TARGET_SOURCE, encoding="utf-8")
    _results_dir(repo).mkdir(parents=True)
    java_bin = tmp_path / "jdk" / "bin"
    java_bin.mkdir(parents=True)
    (java_bin / "java").write_text("#!/bin/sh\n", encoding="utf-8")
    (java_bin / "java").chmod(0o755)

    def fake_git(_repo, args):
        if args[0] == "hash-object":
            return Mock(stdout="c" * 40 + "\n")
        if args[0] == "ls-files":
            return None if args[-1] == TEST_FILE_RELPATH else Mock(stdout="")
        if "diff" in args:
            return Mock(stdout=PATCH_TEXT)
        return Mock(stdout="")

    monkeypatch.setattr(java_evidence, "EVIDENCE_PARENT", tmp_path / "evidence")
    monkeypatch.setattr(java_evidence, "_repository_state",
                        lambda _repo: dict(APP_REPO_STATE))
    monkeypatch.setattr(java_evidence, "java_version", lambda _jdk: JAVA_VERSION_LINE)
    monkeypatch.setattr(java_evidence, "wrapper_version", lambda _repo: WRAPPER_VERSION)
    monkeypatch.setattr(java_evidence, "_git", fake_git)
    return argparse.Namespace(repo=str(repo), jdk=str(tmp_path / "jdk"),
                              module=MODULE, tests=TEST_CLASS,
                              label=LABEL_BASELINE, targets=[TARGET_RELPATH])


@allure.epic("Инфраструктура")
@allure.feature("Локальный harness")
@allure.story("Доказательства Java-прогона")
@allure.severity(allure.severity_level.NORMAL)
class TestJavaRunEvidence:

    @allure.title("Ненулевой baseline сохраняет exit code, свежий JUnit и идентичность исходников")
    def test_baseline_failure_retains_fresh_junit_and_sources(self, java_run, tmp_path, monkeypatch):
        with allure.step("Подменить выполнение падающим baseline-прогоном с JUnit"):
            def execute(args, cwd, env, log_path):
                Path(log_path).write_text("gradle output\n", encoding="utf-8")
                (_results_dir(cwd) / JUNIT_FILENAME).write_text(
                    JUNIT_GRADLE, encoding="utf-8")
                return FAILED_EXIT_CODE
            monkeypatch.setattr(java_evidence, "command", execute)

        with allure.step("Запустить harness и прочитать манифест"):
            result = java_evidence.run_with_evidence(java_run)
            manifest = _manifests(tmp_path)[0]
            content = next((tmp_path / "evidence").glob("run-*/manifest.json")).read_text()

        with allure.step("Проверить код, сводку JUnit и идентичность исходников"):
            assert result == manifest["exit_code"] == FAILED_EXIT_CODE
            assert manifest["status"] == "completed"
            assert manifest["label"] == LABEL_BASELINE
            assert manifest["command"] == EXPECTED_COMMAND
            assert manifest["junit"]["files"] == [f"junit/{JUNIT_FILENAME}"]
            assert manifest["junit"]["summary"] == EXPECTED_SUMMARY
            assert manifest["junit"]["stale_or_missing"] is False
            assert manifest["application"]["commit"] == APP_REPO_STATE["commit"]
            assert manifest["application"]["dirty"] == APP_REPO_STATE["dirty"]
            assert manifest["application"]["gradle_wrapper_version"] == WRAPPER_VERSION
            assert manifest["java"]["version"] == JAVA_VERSION_LINE
            assert manifest["source_identity"]["test_file"] == TEST_FILE_RELPATH
            fingerprints = {item["path"]: item for item in manifest["source_identity"]["files"]}
            assert set(fingerprints) == {TEST_FILE_RELPATH, TARGET_RELPATH}
            assert all(item["sha256"] for item in fingerprints.values())
            assert fingerprints[TEST_FILE_RELPATH]["tracked"] is None
            assert fingerprints[TARGET_RELPATH]["tracked"] is True
            assert manifest["source_identity"]["patch"] == "source.patch"
            assert datetime.fromisoformat(manifest["finished_at"]) >= datetime.fromisoformat(manifest["started_at"])
            assert "private-value" not in content

        with allure.step("Проверить сохранённые копии JUnit, исходников и patch"):
            evidence = next((tmp_path / "evidence").glob("run-*"))
            assert (evidence / "junit" / JUNIT_FILENAME).is_file()
            assert (evidence / "sources" / TEST_FILE_RELPATH).read_text() == TEST_SOURCE
            assert (evidence / "sources" / TARGET_RELPATH).read_text() == TARGET_SOURCE
            assert (evidence / "source.patch").read_text() == PATCH_TEXT
            assert (evidence / "gradle.log").is_file()

    @allure.title("UP-TO-DATE задача и старый JUnit не считаются новым прогоном")
    def test_stale_junit_and_cached_task_are_explicit(self, java_run, tmp_path, monkeypatch):
        with allure.step("Оставить устаревший JUnit и подменить кешированный запуск"):
            (_results_dir(java_run.repo) / JUNIT_FILENAME).write_text(
                JUNIT_GRADLE, encoding="utf-8")
            def execute(args, cwd, env, log_path):
                Path(log_path).write_text(UP_TO_DATE_LOG, encoding="utf-8")
                return SUCCESS_EXIT_CODE
            monkeypatch.setattr(java_evidence, "command", execute)

        with allure.step("Запустить harness и проверить отсутствие свежих результатов"):
            result = java_evidence.run_with_evidence(java_run)
            manifest = _manifests(tmp_path)[0]

        with allure.step("Проверить явную пометку кешированного выполнения"):
            assert result == manifest["exit_code"] == SUCCESS_EXIT_CODE
            assert manifest["status"] == "completed"
            assert manifest["junit"]["files"] == []
            assert manifest["junit"]["summary"] is None
            assert manifest["junit"]["stale_or_missing"] is True
            assert manifest["cached_execution_detected"] is True

    @allure.title("Новый нечитаемый JUnit копируется, но не даёт сводку")
    def test_invalid_fresh_junit_is_copied_without_summary(self, java_run, tmp_path, monkeypatch):
        with allure.step("Подменить прогон повреждённым JUnit"):
            def execute(args, cwd, env, log_path):
                Path(log_path).write_text("gradle output\n", encoding="utf-8")
                (_results_dir(cwd) / JUNIT_FILENAME).write_text(
                    "<testsuite", encoding="utf-8")
                return FAILED_EXIT_CODE
            monkeypatch.setattr(java_evidence, "command", execute)

        with allure.step("Проверить сохранённую ошибку и недоступную сводку"):
            assert java_evidence.run_with_evidence(java_run) == FAILED_EXIT_CODE
            manifest = _manifests(tmp_path)[0]
            assert manifest["junit"]["files"] == [f"junit/{JUNIT_FILENAME}"]
            assert manifest["junit"]["summary"] is None
            assert manifest["junit"]["stale_or_missing"] is False

    @allure.title("Повреждённый XML не позволяет выдать частичную JUnit-сводку за полную")
    def test_mixed_valid_and_invalid_junit_has_no_summary(self, java_run, tmp_path, monkeypatch):
        with allure.step("Подменить прогон корректным и повреждённым XML"):
            def execute(args, cwd, env, log_path):
                Path(log_path).write_text("gradle output\n", encoding="utf-8")
                directory = _results_dir(cwd)
                (directory / JUNIT_FILENAME).write_text(JUNIT_GRADLE, encoding="utf-8")
                (directory / SECOND_JUNIT_FILENAME).write_text(INVALID_JUNIT, encoding="utf-8")
                return FAILED_EXIT_CODE
            monkeypatch.setattr(java_evidence, "command", execute)

        with allure.step("Проверить сохранение обоих XML и отсутствие частичной сводки"):
            assert java_evidence.run_with_evidence(java_run) == FAILED_EXIT_CODE
            manifest = _manifests(tmp_path)[0]
            assert set(manifest["junit"]["files"]) == {
                f"junit/{JUNIT_FILENAME}", f"junit/{SECOND_JUNIT_FILENAME}",
            }
            assert manifest["junit"]["summary"] is None

    @pytest.mark.parametrize("wait_times_out", (False, True))
    @allure.title("Прерывание останавливает собственную группу Gradle до завершения manifest")
    def test_interruption_stops_and_reaps_process_before_finalizing(
            self, java_run, tmp_path, monkeypatch, wait_times_out):
        with allure.step("Подготовить дочерний процесс с прерыванием чтения вывода"):
            process = Mock(pid=PROCESS_PID)
            process.stdout.__iter__ = Mock(side_effect=KeyboardInterrupt)
            process.wait.side_effect = (
                [subprocess.TimeoutExpired(EXPECTED_COMMAND, java_evidence.PROCESS_STOP_TIMEOUT_S),
                 -signal.SIGKILL] if wait_times_out else [-signal.SIGTERM]
            )
            popen = Mock(return_value=process)
            signals = Mock()
            monkeypatch.setattr(java_evidence.subprocess, "Popen", popen)
            monkeypatch.setattr(java_evidence.os, "killpg", signals)
            original_write = java_evidence._write_manifest

            def write_after_stop(path, manifest):
                if manifest["status"] == "interrupted":
                    process.wait.assert_called()
                    process.stdout.close.assert_called_once()
                original_write(path, manifest)
            monkeypatch.setattr(java_evidence, "_write_manifest", write_after_stop)

        with allure.step("Выполнить harness и проверить код прерывания"):
            assert java_evidence.run_with_evidence(java_run) == INTERRUPT_EXIT_CODE
            manifest = _manifests(tmp_path)[0]
            assert manifest["status"] == "interrupted"
            assert manifest["finished_at"] is not None

        with allure.step("Проверить отдельную сессию, остановку только своей группы и ожидание"):
            assert popen.call_args.kwargs["start_new_session"] is True
            assert signals.call_args_list[0].args == (PROCESS_PID, signal.SIGTERM)
            assert signals.call_args_list[-1].args == (PROCESS_PID, signal.SIGKILL)
            assert all(call.args[0] == PROCESS_PID for call in signals.call_args_list)
            process.wait.assert_any_call(timeout=java_evidence.PROCESS_STOP_TIMEOUT_S)
            if wait_times_out:
                process.wait.assert_any_call()

    @pytest.mark.parametrize("failure, expected_code, expected_status", LAUNCH_FAILURE_CASES)
    @allure.title("Ошибка запуска и прерывание оставляют завершённый манифест")
    def test_launch_failure_is_retained(self, java_run, tmp_path, monkeypatch,
                                       failure, expected_code, expected_status):
        with allure.step("Подменить выполнение ошибкой или прерыванием"):
            monkeypatch.setattr(java_evidence, "command", Mock(side_effect=failure))

        with allure.step("Проверить код завершения и сохранённое состояние"):
            assert java_evidence.run_with_evidence(java_run) == expected_code
            manifest = _manifests(tmp_path)[0]
            assert manifest["status"] == expected_status
            assert manifest["exit_code"] == expected_code
            assert manifest["finished_at"] is not None
            assert manifest["junit"]["summary"] is None
            assert manifest["junit"]["stale_or_missing"] is True

    @allure.title("Новый прогон не наследует JUnit предыдущего выполнения")
    def test_runs_are_isolated(self, java_run, tmp_path, monkeypatch):
        with allure.step("Выполнить первый прогон и сохранить его результаты"):
            def execute(args, cwd, env, log_path):
                Path(log_path).write_text("gradle output\n", encoding="utf-8")
                (_results_dir(cwd) / JUNIT_FILENAME).write_text(
                    JUNIT_GRADLE, encoding="utf-8")
                return FAILED_EXIT_CODE
            monkeypatch.setattr(java_evidence, "command", execute)
            java_evidence.run_with_evidence(java_run)

        with allure.step("Выполнить следующий прогон без нового JUnit"):
            def empty_run(args, cwd, env, log_path):
                Path(log_path).write_text("gradle output\n", encoding="utf-8")
                return SUCCESS_EXIT_CODE
            monkeypatch.setattr(java_evidence, "command", empty_run)
            java_evidence.run_with_evidence(java_run)
            manifests = _manifests(tmp_path)

        with allure.step("Проверить разные ID и отсутствие унаследованной сводки"):
            assert len({item["run_id"] for item in manifests}) == len(manifests) == EXPECTED_RUN_COUNT
            assert any(item["junit"]["summary"] == EXPECTED_SUMMARY for item in manifests)
            assert any(item["exit_code"] == SUCCESS_EXIT_CODE
                       and item["junit"]["files"] == []
                       and item["junit"]["summary"] is None for item in manifests)

    @pytest.mark.parametrize("option, value", (("module", INVALID_MODULE),
                                               ("tests", INVALID_SELECTOR)))
    @allure.title("Небезопасные module и selector отклоняются разбором аргументов")
    def test_invalid_selection_rejected(self, option, value):
        with allure.step("Проверить отказ argparse на недопустимое значение"):
            parser = java_evidence.build_parser()
            arguments = ["--repo", "repo", "--jdk", "jdk", "--module", MODULE,
                         "--tests", TEST_CLASS, "--label", LABEL_BASELINE]
            index = arguments.index(f"--{option}") + 1
            arguments[index] = value
            with pytest.raises(SystemExit) as error:
                parser.parse_args(arguments)
            assert error.value.code == ARGPARSE_EXIT_CODE

    @allure.title("Selector с методом и с паттерном разрешается в путь тестового файла")
    def test_test_file_resolution(self, java_run):
        with allure.step("Проверить FQN, FQN с методом и паттерн"):
            repo = Path(java_run.repo)
            assert java_evidence.resolve_test_file(
                repo, MODULE, TEST_CLASS) == TEST_FILE_RELPATH
            assert java_evidence.resolve_test_file(
                repo, MODULE, TEST_SELECTOR_METHOD) == TEST_FILE_RELPATH
            assert java_evidence.resolve_test_file(repo, MODULE, "*ValidationTest") is None
            assert java_evidence.resolve_test_file(repo, MODULE, "absent.Class") is None

    @allure.title("Непригодные входы блокируются до создания evidence")
    def test_invalid_inputs_blocked(self, java_run, tmp_path):
        with allure.step("Проверить блокировку без создания каталогов evidence"):
            java_run.repo = str(tmp_path / "missing")
            assert java_evidence._validate_inputs(java_run) is None
            java_run.repo = str(tmp_path / "app")
            java_run.jdk = str(tmp_path / "missing-jdk")
            assert java_evidence._validate_inputs(java_run) is None
            java_run.jdk = str(tmp_path / "jdk")
            java_run.targets = ["../outside.java"]
            assert java_evidence._validate_inputs(java_run) is None
            java_run.targets = ["absent/Target.java"]
            assert java_evidence._validate_inputs(java_run) is None
            assert not (tmp_path / "evidence").exists()
