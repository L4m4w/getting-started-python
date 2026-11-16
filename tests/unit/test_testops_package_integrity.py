import json
from pathlib import Path

import allure
import pytest

from infrastructure.reporting.testops import results
from test_data.consts.testops_package_integrity import (
    ABSOLUTE_SOURCE, ATTACHMENT_BODY, ATTACHMENT_NAME, BASE_FULL_NAME,
    BOUNDARY_FULL_NAME, BOUND_IDS, CONTAINER_NAME, CORRUPT_JSON,
    ESCAPING_SOURCE, EXPECTED_BIND_ASSIGNMENTS_SHA256,
    EXPECTED_BIND_PACKAGE_SHA256, EXPECTED_INPUT_SHA256,
    EXPECTED_ISOLATE_PACKAGE_SHA256, EXTRA_UUID, FIXTURE_ATTACHMENT,
    FIXTURE_ATTACHMENT_BODY, FOREIGN_FULL_NAME, NESTED_ATTACHMENT,
    NESTED_ATTACHMENT_BODY, NON_OBJECT_JSON, RESULT_TITLE, RESULT_UUIDS,
    SCENARIO_IDS, UNIT_INDEX,
)

REAL_RUNS = ("artifacts/harness/run-5tsmzg1d/allure-results",
             "artifacts/harness/run-vzsatlfk/allure-results")


def _result(scenario_id, uuid=None, steps=None):
    signature = UNIT_INDEX[scenario_id]
    return {"uuid": uuid or RESULT_UUIDS[scenario_id], "name": RESULT_TITLE,
            "status": "passed", "fullName": signature["full_name"],
            "testCaseId": "a" * 32, "historyId": "b" * 32,
            "parameters": [{"name": signature["param"],
                            "value": repr(signature["value"])}],
            "labels": [{"name": "severity", "value": "critical"}],
            "steps": steps or []}


def _results_dir(tmp_path):
    """Детерминированный allure-results: 3 результата, вложения во steps и fixtures."""
    directory = tmp_path / "allure-results"
    directory.mkdir()
    for scenario_id in SCENARIO_IDS:
        steps = []
        if scenario_id == "CAT-UPD-VAL-001":
            steps = [{"name": "outer", "attachments": [
                {"name": "outer", "source": ATTACHMENT_NAME,
                 "type": "text/plain"}], "steps": [
                {"name": "inner", "attachments": [
                    {"name": "inner", "source": NESTED_ATTACHMENT,
                     "type": "text/plain"}]}]}]
        data = _result(scenario_id, steps=steps)
        name = f"{RESULT_UUIDS[scenario_id]}-result.json"
        (directory / name).write_text(json.dumps(data), encoding="utf-8")
    (directory / ATTACHMENT_NAME).write_text(ATTACHMENT_BODY, encoding="utf-8")
    (directory / NESTED_ATTACHMENT).write_text(
        NESTED_ATTACHMENT_BODY, encoding="utf-8")
    (directory / FIXTURE_ATTACHMENT).write_text(
        FIXTURE_ATTACHMENT_BODY, encoding="utf-8")
    container = {"uuid": "container-unit", "children": sorted(RESULT_UUIDS.values()),
                 "befores": [{"name": "fixture", "steps": [
                     {"name": "setup", "attachments": [
                         {"name": "fixture", "source": FIXTURE_ATTACHMENT,
                          "type": "text/plain"}]}]}]}
    (directory / CONTAINER_NAME).write_text(
        json.dumps(container), encoding="utf-8")
    return directory


def _assignments(mode="isolate"):
    return {RESULT_UUIDS[key]: (key, BOUND_IDS[key] if mode == "bind" else None)
            for key in SCENARIO_IDS}


def _snapshot(directory):
    return {path.name: path.read_bytes()
            for path in Path(directory).iterdir() if path.is_file()}


def _leftover_temps(destination):
    return list(Path(destination).parent.glob(
        f".{Path(destination).name}.tmp-*"))


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Строгий разбор результатов")
@allure.severity(allure.severity_level.NORMAL)
class TestStrictScan:

    @allure.title("Повреждённый result JSON прерывает сканирование с именем файла")
    def test_corrupt_result_json_blocks_scan(self, tmp_path):
        with allure.step("Подготовить каталог с битым result-файлом"):
            directory = _results_dir(tmp_path)
            (directory / f"{EXTRA_UUID}-result.json").write_text(
                CORRUPT_JSON, encoding="utf-8")
        with allure.step("Проверить явную ошибку вместо неполного скана"):
            with pytest.raises(results.ResultsIntegrityError,
                               match=f"{EXTRA_UUID}-result.json"):
                results.load_results(directory)

    @allure.title("Result JSON не-объект прерывает сканирование")
    def test_non_object_result_blocks_scan(self, tmp_path):
        with allure.step("Подготовить result-файл со списком вместо объекта"):
            directory = _results_dir(tmp_path)
            (directory / f"{EXTRA_UUID}-result.json").write_text(
                NON_OBJECT_JSON, encoding="utf-8")
        with allure.step("Проверить явную ошибку"):
            with pytest.raises(results.ResultsIntegrityError,
                               match="not an object"):
                results.load_results(directory)

    @allure.title("Отсутствующий uuid не теряет результат, а блокирует скан")
    def test_missing_uuid_is_reported(self, tmp_path):
        with allure.step("Подготовить результат без uuid"):
            directory = _results_dir(tmp_path)
            data = _result("CAT-UPD-VAL-002")
            del data["uuid"]
            (directory / f"{EXTRA_UUID}-result.json").write_text(
                json.dumps(data), encoding="utf-8")
        with allure.step("Проверить ошибку с именем файла"):
            with pytest.raises(results.ResultsIntegrityError,
                               match=f"{EXTRA_UUID}-result.json.*uuid"):
                results.load_results(directory)

    @allure.title("Дублирующий uuid двух файлов блокирует скан")
    def test_duplicate_uuid_blocks_scan(self, tmp_path):
        with allure.step("Подготовить второй файл с тем же uuid"):
            directory = _results_dir(tmp_path)
            twin = _result("CAT-UPD-VAL-002",
                           uuid=RESULT_UUIDS["CAT-UPD-VAL-001"])
            (directory / f"{EXTRA_UUID}-result.json").write_text(
                json.dumps(twin), encoding="utf-8")
        with allure.step("Проверить явную ошибку о дубле"):
            with pytest.raises(results.ResultsIntegrityError,
                               match="duplicate uuid"):
                results.load_results(directory)

    @allure.title("Неизвестный результат блокирует строгое соответствие")
    def test_unknown_result_blocks_strict_mapping(self, tmp_path):
        with allure.step("Добавить результат с чужой сигнатурой"):
            directory = _results_dir(tmp_path)
            foreign = _result("CAT-UPD-VAL-001", uuid=EXTRA_UUID)
            foreign["fullName"] = FOREIGN_FULL_NAME
            (directory / f"{EXTRA_UUID}-result.json").write_text(
                json.dumps(foreign), encoding="utf-8")
        with allure.step("Проверить явную ошибку сканирования"):
            with pytest.raises(results.ResultsIntegrityError,
                               match="matches no scenario"):
                results.scan_assignments(directory, UNIT_INDEX)

    @allure.title("Два результата на один сценарий блокируют соответствие")
    def test_scenario_matched_twice_blocks_strict_mapping(self, tmp_path):
        with allure.step("Добавить дубль сигнатуры сценария 001"):
            directory = _results_dir(tmp_path)
            twin = _result("CAT-UPD-VAL-001", uuid=EXTRA_UUID)
            (directory / f"{EXTRA_UUID}-result.json").write_text(
                json.dumps(twin), encoding="utf-8")
        with allure.step("Проверить явную ошибку"):
            with pytest.raises(results.ResultsIntegrityError,
                               match="already matched"):
                results.scan_assignments(directory, UNIT_INDEX)


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Целостность пакета загрузки")
@allure.severity(allure.severity_level.NORMAL)
class TestPackageIntegrity:

    @allure.title("Результат, добавленный после plan, блокируется по digest и по assignment")
    def test_added_result_after_plan_blocks_build(self, tmp_path):
        with allure.step("Записать digest плана и добавить чужой результат"):
            directory = _results_dir(tmp_path)
            planned = results.results_digest(directory)
            extra = _result("CAT-UPD-VAL-001", uuid=EXTRA_UUID)
            extra["fullName"] = FOREIGN_FULL_NAME
            (directory / f"{EXTRA_UUID}-result.json").write_text(
                json.dumps(extra), encoding="utf-8")
            destination = tmp_path / "pkg"
        with allure.step("Проверить блок по устаревшему digest плана"):
            with pytest.raises(results.ResultsIntegrityError,
                               match="changed since the recorded plan"):
                results.build_package_verified(
                    directory, destination, expected_digest=planned,
                    assignments=_assignments(), index=UNIT_INDEX)
        with allure.step("Проверить блок по отсутствию assignment при свежем digest"):
            with pytest.raises(results.ResultsIntegrityError,
                               match="no assignment"):
                results.build_package_verified(
                    directory, destination,
                    expected_digest=results.results_digest(directory),
                    assignments=_assignments(), index=UNIT_INDEX)

    @allure.title("Изменённый исходный файл не совпадает с digest плана")
    def test_modified_source_blocks_build(self, tmp_path):
        with allure.step("Записать digest и изменить исходный result-файл"):
            directory = _results_dir(tmp_path)
            planned = results.results_digest(directory)
            target = directory / f"{RESULT_UUIDS['CAT-UPD-VAL-001']}-result.json"
            target.write_text(target.read_text() + " ", encoding="utf-8")
        with allure.step("Проверить блок по digest"):
            with pytest.raises(results.ResultsIntegrityError,
                               match="changed since the recorded plan"):
                results.build_package_verified(
                    directory, tmp_path / "pkg", expected_digest=planned,
                    assignments=_assignments(), index=UNIT_INDEX)

    @allure.title("Неполные assignments блокируют сборку")
    def test_incomplete_assignments_block(self, tmp_path):
        with allure.step("Удалить один assignment"):
            directory = _results_dir(tmp_path)
            planned = results.results_digest(directory)
            assignments = _assignments()
            del assignments[RESULT_UUIDS["CAT-UPD-VAL-005"]]
        with allure.step("Проверить явную ошибку"):
            with pytest.raises(results.ResultsIntegrityError,
                               match="no assignment"):
                results.build_package_verified(
                    directory, tmp_path / "pkg", expected_digest=planned,
                    assignments=assignments, index=UNIT_INDEX)

    @allure.title("Лишний assignment на неизвестный uuid блокирует сборку")
    def test_extra_assignment_blocks(self, tmp_path):
        with allure.step("Добавить assignment на отсутствующий результат"):
            directory = _results_dir(tmp_path)
            planned = results.results_digest(directory)
            assignments = _assignments()
            assignments[EXTRA_UUID] = ("CAT-UPD-VAL-001", None)
        with allure.step("Проверить явную ошибку"):
            with pytest.raises(results.ResultsIntegrityError,
                               match="unknown result uuid"):
                results.build_package_verified(
                    directory, tmp_path / "pkg", expected_digest=planned,
                    assignments=assignments, index=UNIT_INDEX)

    @allure.title("Assignment на чужой сценарий расходится со свежим mapping")
    def test_wrong_scenario_assignment_blocks(self, tmp_path):
        with allure.step("Присвоить результату 001 сценарий 002"):
            directory = _results_dir(tmp_path)
            planned = results.results_digest(directory)
            assignments = _assignments()
            assignments[RESULT_UUIDS["CAT-UPD-VAL-001"]] = (
                "CAT-UPD-VAL-002", None)
        with allure.step("Проверить явную ошибку"):
            with pytest.raises(results.ResultsIntegrityError,
                               match="assigned to CAT-UPD-VAL-002"):
                results.build_package_verified(
                    directory, tmp_path / "pkg", expected_digest=planned,
                    assignments=assignments, index=UNIT_INDEX)

    @allure.title("Отсутствующее вложение верхнего уровня блокирует сборку")
    def test_missing_attachment_blocks(self, tmp_path):
        with allure.step("Удалить attachment-файл из каталога"):
            directory = _results_dir(tmp_path)
            (directory / ATTACHMENT_NAME).unlink()
            planned = results.results_digest(directory)
        with allure.step("Проверить явную ошибку"):
            with pytest.raises(results.ResultsIntegrityError,
                               match="missing"):
                results.build_package_verified(
                    directory, tmp_path / "pkg", expected_digest=planned,
                    assignments=_assignments(), index=UNIT_INDEX)

    @allure.title("Отсутствующее вложение во вложенном step блокирует сборку")
    def test_nested_step_attachment_missing_blocks(self, tmp_path):
        with allure.step("Удалить вложение вложенного step"):
            directory = _results_dir(tmp_path)
            (directory / NESTED_ATTACHMENT).unlink()
            planned = results.results_digest(directory)
        with allure.step("Проверить явную ошибку"):
            with pytest.raises(results.ResultsIntegrityError,
                               match="missing"):
                results.build_package_verified(
                    directory, tmp_path / "pkg", expected_digest=planned,
                    assignments=_assignments(), index=UNIT_INDEX)

    @allure.title("Отсутствующее вложение fixture из container блокирует сборку")
    def test_fixture_attachment_missing_blocks(self, tmp_path):
        with allure.step("Удалить вложение befores-фикстуры"):
            directory = _results_dir(tmp_path)
            (directory / FIXTURE_ATTACHMENT).unlink()
            planned = results.results_digest(directory)
        with allure.step("Проверить явную ошибку"):
            with pytest.raises(results.ResultsIntegrityError,
                               match="missing"):
                results.build_package_verified(
                    directory, tmp_path / "pkg", expected_digest=planned,
                    assignments=_assignments(), index=UNIT_INDEX)

    @allure.title("Ссылка вложения за пределы каталога блокирует сборку")
    @pytest.mark.parametrize("source", (ESCAPING_SOURCE, ABSOLUTE_SOURCE))
    def test_escaping_attachment_source_blocks(self, tmp_path, source):
        with allure.step("Подставить выходящую ссылку source в результат"):
            directory = _results_dir(tmp_path)
            target = directory / f"{RESULT_UUIDS['CAT-UPD-VAL-001']}-result.json"
            data = json.loads(target.read_text())
            data["steps"][0]["attachments"][0]["source"] = source
            target.write_text(json.dumps(data), encoding="utf-8")
            planned = results.results_digest(directory)
        with allure.step("Проверить явную ошибку о выходе за каталог"):
            with pytest.raises(results.ResultsIntegrityError,
                               match="escapes"):
                results.build_package_verified(
                    directory, tmp_path / "pkg", expected_digest=planned,
                    assignments=_assignments(), index=UNIT_INDEX)

    @allure.title("Повреждённый container JSON блокирует сборку")
    def test_corrupt_container_blocks_build(self, tmp_path):
        with allure.step("Испортить container-файл"):
            directory = _results_dir(tmp_path)
            (directory / CONTAINER_NAME).write_text(
                CORRUPT_JSON, encoding="utf-8")
            planned = results.results_digest(directory)
        with allure.step("Проверить явную ошибку"):
            with pytest.raises(results.ResultsIntegrityError,
                               match="invalid allure containers"):
                results.build_package_verified(
                    directory, tmp_path / "pkg", expected_digest=planned,
                    assignments=_assignments(), index=UNIT_INDEX)

    @allure.title("Изменение исходника во время сборки блокирует пакет")
    def test_source_change_during_build_blocks(self, tmp_path, monkeypatch):
        with allure.step("Подменить повторный digest на изменённый"):
            directory = _results_dir(tmp_path)
            planned = results.results_digest(directory)
            real = results.results_digest
            calls = []

            def drifting(path):
                value = real(path)
                if Path(path) == directory:
                    calls.append(value)
                    if len(calls) == 2:
                        return "0" * 64
                return value
            monkeypatch.setattr(results, "results_digest", drifting)
        with allure.step("Проверить явную ошибку сборки"):
            with pytest.raises(results.ResultsIntegrityError,
                               match="changed while the package"):
                results.build_package_verified(
                    directory, tmp_path / "pkg", expected_digest=planned,
                    assignments=_assignments(), index=UNIT_INDEX)

    @allure.title("Ошибка сборки не оставляет частичного пакета и хранит старый")
    def test_failed_build_leaves_no_partial_package(self, tmp_path):
        with allure.step("Собрать первый пакет и зафиксировать его вид"):
            directory = _results_dir(tmp_path)
            planned = results.results_digest(directory)
            destination = tmp_path / "pkg"
            info = results.build_package_verified(
                directory, destination, expected_digest=planned,
                assignments=_assignments(), index=UNIT_INDEX)
            old_snapshot = _snapshot(destination)
        with allure.step("Испортить источник и попытаться пересобрать"):
            (directory / f"{EXTRA_UUID}-result.json").write_text(
                CORRUPT_JSON, encoding="utf-8")
            with pytest.raises(results.ResultsIntegrityError):
                results.build_package_verified(
                    directory, destination, expected_digest=planned,
                    assignments=_assignments(), index=UNIT_INDEX)
            with pytest.raises(results.ResultsIntegrityError):
                results.build_package_verified(
                    directory, destination,
                    expected_digest=results.results_digest(directory),
                    assignments=_assignments(), index=UNIT_INDEX)
        with allure.step("Проверить целостность старого пакета и отсутствие tmp"):
            assert destination.is_dir()
            assert _snapshot(destination) == old_snapshot
            assert results.results_digest(destination) == info["sha256"]
            assert _leftover_temps(destination) == []
        with allure.step("Проверить, что при ошибке новый каталог не создан"):
            fresh = tmp_path / "pkg2"
            with pytest.raises(results.ResultsIntegrityError):
                results.build_package_verified(
                    directory, fresh,
                    expected_digest=results.results_digest(directory),
                    assignments=_assignments(), index=UNIT_INDEX)
            assert not fresh.exists()
            assert _leftover_temps(fresh) == []


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Идентичность пакета")
@allure.severity(allure.severity_level.NORMAL)
class TestPackageIdentity:

    @allure.title("Один вход и mapping дают одинаковый пакет с golden-идентичностью")
    def test_deterministic_build_matches_golden_digests(self, tmp_path):
        with allure.step("Собрать isolate-пакет дважды из неизменного входа"):
            directory = _results_dir(tmp_path)
            planned = results.results_digest(directory)
            first = results.build_package_verified(
                directory, tmp_path / "pkg-a", expected_digest=planned,
                assignments=_assignments(), index=UNIT_INDEX)
            second = results.build_package_verified(
                directory, tmp_path / "pkg-b", expected_digest=planned,
                assignments=_assignments(), index=UNIT_INDEX)
        with allure.step("Проверить равенство digest и golden-значений"):
            assert first["sha256"] == second["sha256"]
            assert first["input_sha256"] == second["input_sha256"]
            assert (first["assignments_sha256"]
                    == second["assignments_sha256"])
            assert first["input_sha256"] == EXPECTED_INPUT_SHA256
            assert first["sha256"] == EXPECTED_ISOLATE_PACKAGE_SHA256
            bind = results.build_package_verified(
                directory, tmp_path / "pkg-c", expected_digest=planned,
                assignments=_assignments("bind"), index=UNIT_INDEX)
            assert bind["sha256"] == EXPECTED_BIND_PACKAGE_SHA256
            assert (bind["assignments_sha256"]
                    == EXPECTED_BIND_ASSIGNMENTS_SHA256)

    @allure.title("Изменение bindings меняет идентичность пакета")
    def test_binding_change_changes_package_identity(self, tmp_path):
        with allure.step("Собрать isolate- и bind-пакеты одного входа"):
            directory = _results_dir(tmp_path)
            planned = results.results_digest(directory)
            isolate = results.build_package_verified(
                directory, tmp_path / "pkg-a", expected_digest=planned,
                assignments=_assignments("isolate"), index=UNIT_INDEX)
            bind = results.build_package_verified(
                directory, tmp_path / "pkg-b", expected_digest=planned,
                assignments=_assignments("bind"), index=UNIT_INDEX)
        with allure.step("Проверить различие идентичностей при том же входе"):
            assert isolate["input_sha256"] == bind["input_sha256"]
            assert isolate["sha256"] != bind["sha256"]
            assert (isolate["assignments_sha256"]
                    != bind["assignments_sha256"])

    @allure.title("Сборка никогда не изменяет исходные allure-файлы")
    def test_source_never_modified(self, tmp_path):
        with allure.step("Зафиксировать байты исходного каталога и собрать пакет"):
            directory = _results_dir(tmp_path)
            before = _snapshot(directory)
            results.build_package_verified(
                directory, tmp_path / "pkg",
                expected_digest=results.results_digest(directory),
                assignments=_assignments("bind"), index=UNIT_INDEX)
        with allure.step("Проверить побайтовое совпадение источника"):
            assert _snapshot(directory) == before


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Проверка пакета перед upload")
@allure.severity(allure.severity_level.NORMAL)
class TestPackageVerification:

    @allure.title("verify_package/verify_source_digest принимают неизменный пакет")
    def test_verification_passes_on_intact_package(self, tmp_path):
        with allure.step("Собрать пакет и проверить оба digest"):
            directory = _results_dir(tmp_path)
            planned = results.results_digest(directory)
            destination = tmp_path / "pkg"
            info = results.build_package_verified(
                directory, destination, expected_digest=planned,
                assignments=_assignments(), index=UNIT_INDEX)
        with allure.step("Проверить отсутствие ошибок верификации"):
            results.verify_package(destination, info["sha256"])
            results.verify_source_digest(directory, info["input_sha256"])

    @allure.title("Изменённый после сборки пакет и источник блокируются")
    def test_verification_blocks_changed_package_and_source(self, tmp_path):
        with allure.step("Собрать пакет и изменить пакет и источник"):
            directory = _results_dir(tmp_path)
            planned = results.results_digest(directory)
            destination = tmp_path / "pkg"
            info = results.build_package_verified(
                directory, destination, expected_digest=planned,
                assignments=_assignments(), index=UNIT_INDEX)
            packaged = next(destination.glob(f"*{results.RESULT_SUFFIX}"))
            packaged.write_text(packaged.read_text() + " ", encoding="utf-8")
            (directory / ATTACHMENT_NAME).write_text(
                ATTACHMENT_BODY + " ", encoding="utf-8")
        with allure.step("Проверить явные ошибки верификации"):
            with pytest.raises(results.ResultsIntegrityError,
                               match="changed after build"):
                results.verify_package(destination, info["sha256"])
            with pytest.raises(results.ResultsIntegrityError,
                               match="changed since the package was built"):
                results.verify_source_digest(directory, info["input_sha256"])


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Записанные прогоны как read-only вход")
@allure.severity(allure.severity_level.NORMAL)
class TestRecordedEvidence:

    @allure.title("Строгий скан и проверка вложений проходят на записанных прогонах")
    @pytest.mark.parametrize("relative", REAL_RUNS)
    def test_recorded_runs_pass_strict_scan(self, relative):
        with allure.step("Найти записанный прогон или пропустить проверку"):
            directory = Path(relative)
            if not directory.is_dir():
                pytest.skip(f"no recorded evidence at {relative}")
            from tools import testops
        with allure.step("Проверить строгое соответствие и вложения"):
            mapping = results.scan_assignments(directory,
                                               testops._scenario_index())
            scanned = results.load_results(directory)
            results.validate_attachments(directory, scanned)
        with allure.step("Проверить, что каждый результат получил сценарий"):
            assert len(mapping) == len(scanned)
            assert set(mapping.values()) <= set(testops._scenario_index())
