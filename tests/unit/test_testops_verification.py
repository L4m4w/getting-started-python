import copy
import json
from pathlib import Path

import allure
import pytest

from infrastructure.reporting.testops import (
    lifecycle, state as state_mod, verification,
)
from test_data.consts import testops_verification as tv


def _scenarios(bound=True):
    scenarios = {}
    for index, scenario_id in enumerate(tv.SCENARIO_IDS):
        scenarios[scenario_id] = {
            "uuid": f"uuid-{index}-{scenario_id}",
            "status": tv.SCENARIO_STATUSES[scenario_id],
            "testops_id": tv.BOUND_IDS[scenario_id] if bound else None,
            "binding": "bound" if bound else "unresolved",
            "binding_source": "assign" if bound else None,
        }
    return scenarios


def _write_state(tmp_path, upload=None, launch="recorded", scenarios=None):
    state_dir = tmp_path / "testops" / tv.EXECUTION_ID
    state_dir.mkdir(parents=True)
    state = state_mod.new_state(tv.EXECUTION_ID, tv.ENDPOINT, tv.PROJECT_ID)
    state["scenarios"] = scenarios if scenarios is not None \
        else _scenarios()
    if launch == "recorded":
        state["launch"] = {"id": tv.LAUNCH_ID, "name": tv.LAUNCH_NAME,
                           "url": tv.LAUNCH_URL, "created_at": "t"}
    elif launch is not None:
        state["launch"] = launch
    state["upload"].update(
        {"status": "sent", "attempts": 1, **(upload or {})})
    state_mod.save_state(state_dir, state)
    return state_dir


def _expected(bound=True):
    return state_mod.expected_scenarios(
        {"scenarios": _scenarios(bound)})


def _read(state_dir):
    return json.loads((Path(state_dir) / "state.json").read_text())


class FakeProbe:
    """Подмена read_snapshot: фиксированный dict, callable или ошибка."""

    def __init__(self, snapshot=None, error=None):
        self.snapshot = snapshot
        self.error = error
        self.calls = []

    def read_snapshot(self, endpoint, launch_id):
        self.calls.append((endpoint, launch_id))
        if self.error is not None:
            raise self.error
        if callable(self.snapshot):
            return self.snapshot(endpoint, launch_id)
        return self.snapshot


class RecordingLock:
    """Context manager, фиксирующий границы удержания блокировки."""

    def __init__(self):
        self.held = False
        self.events = []

    def __enter__(self):
        self.held = True
        self.events.append("acquire")
        return self

    def __exit__(self, *exc):
        self.events.append("release")
        self.held = False
        return False


def _verify(state_dir, probe, **kwargs):
    return verification.perform_snapshot_verify(state_dir, probe, **kwargs)


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Контракт REST-снимка launch")
@allure.severity(allure.severity_level.NORMAL)
class TestSnapshotContract:

    @allure.title("Malformed snapshot никогда не подтверждает upload")
    def test_malformed_snapshot_is_inconclusive(self, tmp_path):
        with allure.step("Проверить не-словарь и неизвестный outcome"):
            for bad in (None, "text", [], {"outcome": "strange"}):
                assessment = verification.evaluate_snapshot(
                    bad, {}, launch_id=tv.LAUNCH_ID,
                    project_id=tv.PROJECT_ID)
                assert assessment.verdict == \
                    verification.VERDICT_INCONCLUSIVE
        with allure.step("Проверить complete без обязательных полей"):
            no_pagination = tv.snapshot()
            no_pagination.pop("pagination")
            for bad in ({"outcome": "complete"},
                        no_pagination,
                        tv.snapshot(stats="text"),
                        tv.snapshot(ready="yes")):
                assessment = verification.evaluate_snapshot(
                    bad, _expected(),
                    launch_id=tv.LAUNCH_ID, project_id=tv.PROJECT_ID)
                assert assessment.verdict == \
                    verification.VERDICT_INCONCLUSIVE
                assert assessment.checks["contract"] == "malformed"
        with allure.step("Проверить строку result без обязательных полей"):
            snapshot = tv.snapshot()
            snapshot["results"][0].pop("hidden")
            assessment = verification.evaluate_snapshot(
                snapshot, _expected(),
                launch_id=tv.LAUNCH_ID, project_id=tv.PROJECT_ID)
            assert assessment.verdict == verification.VERDICT_INCONCLUSIVE
        with allure.step("Проверить, что состояние sent не изменилось"):
            state_dir = _write_state(tmp_path)
            run = _verify(state_dir, FakeProbe({"outcome": "complete"}))
            assert run.confirmed is False
            assert _read(state_dir)["upload"]["status"] == "sent"

    @allure.title("Outcome probe передаётся честно: missing, unreachable, inconclusive")
    def test_probe_outcomes_pass_through(self, tmp_path):
        with allure.step("missing → verdict missing и статус unknown"):
            state_dir = _write_state(tmp_path / "m")
            run = _verify(state_dir, FakeProbe(
                tv.snapshot(outcome="missing", launch=None, stats=None,
                            ready=None)))
            assert run.verdict == verification.VERDICT_MISSING
            assert _read(state_dir)["upload"]["status"] == "unknown"
        with allure.step("unreachable и inconclusive не меняют статус"):
            for index, outcome in enumerate(
                    ("unreachable", "inconclusive")):
                state_dir = _write_state(tmp_path / f"o{index}")
                run = _verify(state_dir, FakeProbe(
                    tv.snapshot(outcome=outcome)))
                assert run.verdict == outcome
                assert _read(state_dir)["upload"]["status"] == "sent"


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Подтверждение и противоречия snapshot")
@allure.severity(allure.severity_level.NORMAL)
class TestConfirmedAndContradictions:

    @allure.title("Полный корректный bind snapshot переводит в uploaded")
    def test_full_bind_snapshot_confirms(self, tmp_path):
        with allure.step("Выполнить verify с полным snapshot"):
            state_dir = _write_state(tmp_path)
            probe = FakeProbe(tv.snapshot())
            run = _verify(state_dir, probe)
            state = _read(state_dir)
        with allure.step("Проверить confirmed, вызов probe и uploaded"):
            assert run.verdict == verification.VERDICT_CONFIRMED
            assert run.confirmed is True
            assert probe.calls == [(tv.ENDPOINT, tv.LAUNCH_ID)]
            assert state["upload"]["status"] == "uploaded"
            confirmation = state["upload"]["confirmation"]
            assert confirmation["verdict"] == "confirmed"
            assert confirmation["method"] == "rest-snapshot"
            assert confirmation["checks"]["result_set"] == "match"

    @allure.title("Сохраняемое evidence дистиллировано: без имён и тел результатов")
    def test_persisted_evidence_is_distilled(self, tmp_path):
        with allure.step("Выполнить confirmed verify"):
            state_dir = _write_state(tmp_path)
            _verify(state_dir, FakeProbe(tv.snapshot()))
            confirmation = _read(state_dir)["upload"]["confirmation"]
        with allure.step("Проверить отсутствие сырых данных в checks"):
            payload = json.dumps(confirmation)
            assert tv.RESULT_TITLE not in payload
            assert "results" not in confirmation["checks"]
            assert confirmation["checks"]["matched"] == \
                sorted(tv.SCENARIO_IDS)

    @allure.title("Неверный launch ID или проект — contradiction и unknown")
    def test_wrong_launch_and_project(self, tmp_path):
        with allure.step("snapshot с чужим launch id"):
            state_dir = _write_state(tmp_path / "l")
            run = _verify(state_dir, FakeProbe(
                tv.snapshot(launch_id=tv.OTHER_LAUNCH_ID)))
            assert run.verdict == verification.VERDICT_CONTRADICTION
            assert _read(state_dir)["upload"]["status"] == "unknown"
        with allure.step("snapshot с чужим project id"):
            state_dir = _write_state(tmp_path / "p")
            run = _verify(state_dir, FakeProbe(
                tv.snapshot(project_id=tv.OTHER_PROJECT_ID)))
            assert run.verdict == verification.VERDICT_CONTRADICTION
            assert run.checks["project_match"] is False
        with allure.step("строка результата с чужим launch/project"):
            state_dir = _write_state(tmp_path / "r")
            rows = tv.rows()
            rows[1] = tv.result_row(2, "CAT-UPD-VAL-002",
                                    launch_id=tv.OTHER_LAUNCH_ID)
            run = _verify(state_dir, FakeProbe(
                tv.snapshot(rows, total="auto")))
            assert run.verdict == verification.VERDICT_CONTRADICTION

    @allure.title("Неверный статус или case binding — contradiction")
    def test_wrong_status_and_case(self, tmp_path):
        with allure.step("строка со статусом, отличным от ожидаемого"):
            state_dir = _write_state(tmp_path / "s")
            rows = tv.rows()
            rows[0]["status"] = "failed"
            run = _verify(state_dir, FakeProbe(tv.snapshot(rows)))
            assert run.verdict == verification.VERDICT_CONTRADICTION
        with allure.step("строка, привязанная к чужому кейсу"):
            state_dir = _write_state(tmp_path / "c")
            rows = tv.rows()
            rows[0]["test_case_id"] += 5000
            run = _verify(state_dir, FakeProbe(tv.snapshot(rows)))
            assert run.verdict == verification.VERDICT_CONTRADICTION
            assert _read(state_dir)["upload"]["status"] == "unknown"

    @allure.title("CAT-UPD-VAL-0010 не совпадает с CAT-UPD-VAL-001 — foreign")
    def test_sid_lookalike_is_foreign_not_a_match(self, tmp_path):
        with allure.step("Строка 001 переименована в похожий 0010"):
            state_dir = _write_state(tmp_path)
            rows = tv.rows()
            rows[0]["name"] = f"{tv.SID_LOOKALIKE}: {tv.RESULT_TITLE}"
            run = _verify(state_dir, FakeProbe(tv.snapshot(rows)))
        with allure.step("Проверить contradiction, foreign и missing 001"):
            assert run.verdict == verification.VERDICT_CONTRADICTION
            assert run.checks["foreign"] == 1
            assert run.checks["missing"] == ["CAT-UPD-VAL-001"]
            assert "CAT-UPD-VAL-001" not in run.checks["matched"]

    @allure.title("Лишняя строка результата — contradiction")
    def test_extra_foreign_row(self, tmp_path):
        with allure.step("Добавить строку с неизвестным именем"):
            state_dir = _write_state(tmp_path)
            rows = tv.rows() + [
                tv.result_row(9, "CAT-UPD-VAL-001",
                              name=f"ZZZ-OTHER-1: {tv.RESULT_TITLE}",
                              case_id=None)]
            run = _verify(state_dir, FakeProbe(tv.snapshot(rows)))
        with allure.step("Проверить contradiction"):
            assert run.verdict == verification.VERDICT_CONTRADICTION
            assert run.checks["foreign"] == 1

    @allure.title("Статистика больше ожидаемой — contradiction")
    def test_overdelivered_stats(self, tmp_path):
        with allure.step("snapshot со статистикой сверх ожидаемой"):
            state_dir = _write_state(tmp_path)
            run = _verify(state_dir, FakeProbe(
                tv.snapshot(stats={"passed": 2, "failed": 1,
                                   "skipped": 1})))
        with allure.step("Проверить contradiction"):
            assert run.verdict == verification.VERDICT_CONTRADICTION
            assert run.checks["result_set"] == "overdelivered"

    @allure.title("Статистика не сходится со строками — contradiction")
    def test_stats_inconsistent_with_rows(self, tmp_path):
        with allure.step("Полная статистика при двух строках"):
            state_dir = _write_state(tmp_path)
            run = _verify(state_dir, FakeProbe(
                tv.snapshot(tv.rows()[:2])))
        with allure.step("Проверить contradiction, а не partial"):
            assert run.verdict == verification.VERDICT_CONTRADICTION
            assert run.checks["stats_consistent"] is False


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Неполнота и аномалии snapshot")
@allure.severity(allure.severity_level.NORMAL)
class TestIncompleteAndAnomalies:

    @allure.title("closed=false и ready=false/None — неполное подтверждение")
    def test_unclosed_or_unready_launch(self, tmp_path):
        with allure.step("Проверить каждый незавершённый вариант"):
            variants = (tv.snapshot(closed=False),
                        tv.snapshot(ready=False),
                        tv.snapshot(ready=None))
            for index, snapshot in enumerate(variants):
                state_dir = _write_state(tmp_path / f"v{index}")
                run = _verify(state_dir, FakeProbe(snapshot))
                assert run.verdict == verification.VERDICT_INCONCLUSIVE
                assert _read(state_dir)["upload"]["status"] == "sent"

    @allure.title("Неполная и несогласованная пагинация — inconclusive")
    def test_incomplete_pagination(self, tmp_path):
        with allure.step("complete=false и total != числу строк"):
            for index, snapshot in enumerate(
                    (tv.snapshot(complete=False),
                     tv.snapshot(total=99))):
                state_dir = _write_state(tmp_path / f"p{index}")
                run = _verify(state_dir, FakeProbe(snapshot))
                assert run.verdict == verification.VERDICT_INCONCLUSIVE
        with allure.step("Проверить метки пагинации"):
            assert run.checks["pagination"] == "inconsistent"

    @allure.title("Статусы in_progress/unknown — обработка не завершена")
    def test_in_flight_statuses(self, tmp_path):
        with allure.step("Строки со статусами in_progress и unknown"):
            for index, status in enumerate(
                    ("in_progress", "unknown")):
                state_dir = _write_state(tmp_path / f"f{index}")
                rows = tv.rows()
                rows[1]["status"] = status
                run = _verify(state_dir, FakeProbe(tv.snapshot(rows)))
                assert run.verdict == verification.VERDICT_INCONCLUSIVE
                assert _read(state_dir)["upload"]["status"] == "sent"

    @allure.title("hidden и retry-строки — аномалия без выбора последнего")
    def test_hidden_and_retried_rows(self, tmp_path):
        with allure.step("Строка hidden=true"):
            state_dir = _write_state(tmp_path / "h")
            rows = tv.rows()
            rows[0]["hidden"] = True
            run = _verify(state_dir, FakeProbe(tv.snapshot(rows)))
            assert run.verdict == verification.VERDICT_INCONCLUSIVE
            assert run.checks["anomalies"]
        with allure.step("Строка, замещённая retry"):
            state_dir = _write_state(tmp_path / "r")
            rows = tv.rows()
            rows[0]["retried_by_id"] = tv.RESULT_ID_BASE + 50
            run = _verify(state_dir, FakeProbe(tv.snapshot(rows)))
            assert run.verdict == verification.VERDICT_INCONCLUSIVE
            assert run.checks["anomalies"]

    @allure.title("Дубль result ID и вторая строка сценария — аномалия")
    def test_duplicate_rows_are_anomalies(self, tmp_path):
        with allure.step("Две строки с одинаковым result id"):
            state_dir = _write_state(tmp_path / "i")
            rows = tv.rows()
            rows[1]["id"] = rows[0]["id"]
            run = _verify(state_dir, FakeProbe(tv.snapshot(rows)))
            assert run.verdict == verification.VERDICT_INCONCLUSIVE
            assert any("duplicate result id" in item
                       for item in run.checks["anomalies"])
        with allure.step("Вторая строка на тот же сценарий"):
            state_dir = _write_state(tmp_path / "s")
            rows = tv.rows() + [
                tv.result_row(8, "CAT-UPD-VAL-001")]
            run = _verify(state_dir, FakeProbe(tv.snapshot(rows)))
            assert run.verdict == verification.VERDICT_INCONCLUSIVE
            assert any("second row" in item
                       for item in run.checks["anomalies"])

    @allure.title("Отсутствующий сценарий — partial, статус unknown без resend")
    def test_missing_scenario_is_partial(self, tmp_path):
        with allure.step("Две строки и соответствующая часть статистики"):
            state_dir = _write_state(tmp_path)
            run = _verify(state_dir, FakeProbe(tv.snapshot(
                tv.rows()[:2], stats={"passed": 1, "failed": 1})))
            state = _read(state_dir)
        with allure.step("Проверить partial и блокировку повтора"):
            assert run.verdict == verification.VERDICT_PARTIAL
            assert run.checks["missing"] == ["CAT-UPD-VAL-003"]
            assert state["upload"]["status"] == "unknown"
            retry = lifecycle.perform_upload(
                state_dir, FakeProbe(), launch_name=tv.LAUNCH_NAME,
                retry=True)
            assert retry.outcome == lifecycle.OUTCOME_BLOCKED

    @allure.title("Пустой launch не разрешает повторную отправку")
    def test_empty_launch_keeps_resend_blocked(self, tmp_path):
        with allure.step("snapshot без строк и с нулевой статистикой"):
            state_dir = _write_state(tmp_path)
            run = _verify(state_dir, FakeProbe(tv.snapshot(
                [], stats={"passed": 0, "failed": 0, "skipped": 0})))
            state = _read(state_dir)
        with allure.step("Проверить empty и блок повтора"):
            assert run.verdict == verification.VERDICT_EMPTY
            assert state["upload"]["status"] == "unknown"
            assert lifecycle.decide_upload(state, retry=True)[0] is False

    @allure.title("Нечитаемая статистика — inconclusive без понижения")
    def test_unreadable_stats(self, tmp_path):
        with allure.step("snapshot со stats=None"):
            state_dir = _write_state(tmp_path)
            run = _verify(state_dir, FakeProbe(
                tv.snapshot(stats=None)))
        with allure.step("Проверить inconclusive и сохранённый sent"):
            assert run.verdict == verification.VERDICT_INCONCLUSIVE
            assert run.checks["result_set"] == "inconclusive"
            assert _read(state_dir)["upload"]["status"] == "sent"


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Режимы привязки кейсов")
@allure.severity(allure.severity_level.NORMAL)
class TestBindingModes:

    @allure.title("Isolate: найденные case ID — кандидаты, без автоподтверждения")
    def test_isolate_unbound_not_confirmed(self, tmp_path):
        with allure.step("Состояние без bindings, строки с case ID"):
            state_dir = _write_state(
                tmp_path, scenarios=_scenarios(bound=False))
            run = _verify(state_dir, FakeProbe(
                tv.snapshot("candidate")))
            state = _read(state_dir)
        with allure.step("Проверить inconclusive и записанных кандидатов"):
            assert run.verdict == verification.VERDICT_INCONCLUSIVE
            assert run.confirmed is False
            assert state["upload"]["status"] == "sent"
            candidates = run.checks["candidates"]
            assert candidates["CAT-UPD-VAL-001"] == \
                tv.CANDIDATE_CASE_ID + 1

    @allure.title("Строка без привязки в isolate — аномалия")
    def test_isolate_unlinked_row_is_anomaly(self, tmp_path):
        with allure.step("Строки без test_case_id"):
            state_dir = _write_state(
                tmp_path, scenarios=_scenarios(bound=False))
            run = _verify(state_dir, FakeProbe(
                tv.snapshot(tv.rows(None))))
        with allure.step("Проверить inconclusive"):
            assert run.verdict == verification.VERDICT_INCONCLUSIVE
            assert run.checks["anomalies"]

    @allure.title("Частичная привязка не подтверждает upload")
    def test_partial_binding_not_confirmed(self, tmp_path):
        with allure.step("Один сценарий bound, остальные без ID"):
            scenarios = _scenarios(bound=False)
            scenarios["CAT-UPD-VAL-001"].update(
                testops_id=tv.BOUND_IDS["CAT-UPD-VAL-001"],
                binding="bound", binding_source="assign")
            state_dir = _write_state(tmp_path, scenarios=scenarios)
            rows = tv.rows("candidate")
            rows[0]["test_case_id"] = tv.BOUND_IDS["CAT-UPD-VAL-001"]
            run = _verify(state_dir, FakeProbe(tv.snapshot(rows)))
        with allure.step("Проверить inconclusive"):
            assert run.verdict == verification.VERDICT_INCONCLUSIVE
            assert run.confirmed is False


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Оркестрация verify под блокировкой")
@allure.severity(allure.severity_level.NORMAL)
class TestVerifyOrchestration:

    @allure.title("Lock охватывает загрузку, probe, решение и сохранение")
    def test_lock_covers_probe_and_persist(self, tmp_path):
        with allure.step("Подменить lock, probe и persist записями"):
            state_dir = _write_state(tmp_path)
            lock = RecordingLock()
            snapshots = []

            def persist(state):
                assert lock.held, "persist вызван вне блокировки"
                snapshots.append(copy.deepcopy(state))
                lock.events.append("persist")
                state_mod.save_state(state_dir, state)

            def probe_call(endpoint, launch_id):
                assert lock.held, "probe вызван вне блокировки"
                lock.events.append("probe")
                return tv.snapshot()

            run = _verify(state_dir, FakeProbe(probe_call),
                          persist=persist, lock=lock)
        with allure.step("Проверить порядок: acquire → probe → persist → release"):
            assert run.confirmed is True
            assert lock.events == ["acquire", "probe", "persist",
                                   "release"]
            assert lock.held is False

    @allure.title("Уже захваченный ExecutionLock используется без повторного захвата")
    def test_held_execution_lock_is_reused(self, tmp_path):
        with allure.step("Захватить ExecutionLock снаружи и передать его"):
            state_dir = _write_state(tmp_path)
            lock = lifecycle.ExecutionLock(state_dir, "verify")
            lock.acquire()
            try:
                run = _verify(state_dir, FakeProbe(tv.snapshot()),
                              lock=lock)
                assert run.confirmed is True
                assert lock._held, "внешний lock не должен сниматься"
            finally:
                lock.release()
            assert not (Path(state_dir) / "execution.lock").exists()

    @allure.title("Повреждённый state блокирует verify без перезаписи")
    def test_corrupt_state_blocks(self, tmp_path):
        with allure.step("Записать битый state.json"):
            state_dir = tmp_path / "testops" / tv.EXECUTION_ID
            state_dir.mkdir(parents=True)
            path = Path(state_dir) / "state.json"
            path.write_text("{not json", encoding="utf-8")
        with allure.step("Проверить исключение и сохранность файла"):
            with pytest.raises(state_mod.StateCorruptError):
                _verify(state_dir, FakeProbe(tv.snapshot()))
            assert path.read_text(encoding="utf-8") == "{not json"

    @allure.title("uploaded терминален: probe не вызывается, повтор запрещён")
    def test_uploaded_is_terminal(self, tmp_path):
        with allure.step("Состояние uploaded с записанным launch"):
            state_dir = _write_state(
                tmp_path, upload={"status": "uploaded"})
            before = _read(state_dir)
            probe = FakeProbe(tv.snapshot())
            run = _verify(state_dir, probe)
        with allure.step("Проверить confirmed без вызова probe"):
            assert run.confirmed is True
            assert run.status == "uploaded"
            assert probe.calls == []
            assert _read(state_dir) == before
        with allure.step("Проверить, что повторная отправка невозможна"):
            retry = lifecycle.perform_upload(
                state_dir, FakeProbe(), launch_name=tv.LAUNCH_NAME,
                retry=True)
            assert retry.outcome == lifecycle.OUTCOME_BLOCKED

    @allure.title("in_progress не подтверждается автоматически")
    def test_in_progress_not_confirmed(self, tmp_path):
        with allure.step("Состояние in_progress с записанным launch"):
            state_dir = _write_state(
                tmp_path, upload={"status": "in_progress"})
            before = _read(state_dir)
            probe = FakeProbe(tv.snapshot())
            run = _verify(state_dir, probe)
        with allure.step("Проверить inconclusive без probe и изменений"):
            assert run.verdict == verification.VERDICT_INCONCLUSIVE
            assert run.confirmed is False
            assert probe.calls == []
            assert _read(state_dir) == before

    @allure.title("Нет state или нет launch ID — inconclusive без probe")
    def test_no_state_no_launch(self, tmp_path):
        with allure.step("Отсутствующий state"):
            run = _verify(tmp_path / "empty", FakeProbe())
            assert run.verdict == verification.VERDICT_INCONCLUSIVE
        with allure.step("State без записанного launch"):
            state_dir = _write_state(tmp_path / "n", launch=None)
            probe = FakeProbe(tv.snapshot())
            run = _verify(state_dir, probe)
            assert run.verdict == verification.VERDICT_INCONCLUSIVE
            assert probe.calls == []

    @allure.title("Переданный launch ID, отличный от записанного — contradiction")
    def test_passed_launch_id_mismatch(self, tmp_path):
        with allure.step("verify с чужим --launch-id"):
            state_dir = _write_state(tmp_path)
            probe = FakeProbe(tv.snapshot())
            run = _verify(state_dir, probe,
                          launch_id=tv.OTHER_LAUNCH_ID)
        with allure.step("Проверить contradiction и unknown"):
            assert run.verdict == verification.VERDICT_CONTRADICTION
            assert probe.calls == []
            assert _read(state_dir)["upload"]["status"] == "unknown"

    @allure.title("Прерывание и исключение probe — unreachable без записи")
    def test_probe_interruption_and_error(self, tmp_path):
        with allure.step("probe бросает KeyboardInterrupt"):
            state_dir = _write_state(tmp_path / "k")
            run = _verify(state_dir, FakeProbe(
                error=KeyboardInterrupt()))
            assert run.verdict == verification.VERDICT_UNREACHABLE
        with allure.step("probe бросает произвольное исключение"):
            state_dir = _write_state(tmp_path / "e")
            run = _verify(state_dir, FakeProbe(
                error=ConnectionError("boom")))
            assert run.verdict == verification.VERDICT_UNREACHABLE
            assert _read(state_dir)["upload"]["status"] == "sent"

    @allure.title("Probe без метода read_snapshot — inconclusive")
    def test_probe_without_read_snapshot(self, tmp_path):
        with allure.step("Передать объект без метода"):
            state_dir = _write_state(tmp_path)
            run = _verify(state_dir, object())
        with allure.step("Проверить inconclusive и сохранённый sent"):
            assert run.verdict == verification.VERDICT_INCONCLUSIVE
            assert _read(state_dir)["upload"]["status"] == "sent"


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Проверки интеграции координатора")
class TestCoordinatorContract:

    @allure.title("Отсутствующие nullable-поля не обходят проверку контракта")
    @pytest.mark.parametrize("field", ("ready", "stats", "reason"))
    def test_missing_snapshot_field(self, field):
        with allure.step("Удалить обязательное поле полного снимка"):
            snapshot = tv.snapshot()
            snapshot.pop(field)
        with allure.step("Проверить inconclusive вместо исключения или успеха"):
            result = verification.evaluate_snapshot(
                snapshot, _expected(), launch_id=tv.LAUNCH_ID,
                project_id=tv.PROJECT_ID)
            assert result.verdict == verification.VERDICT_INCONCLUSIVE
            assert result.confirmed is False

    @allure.title("Отсутствующие nullable-поля строки блокируют подтверждение")
    @pytest.mark.parametrize("field", ("test_case_id", "retried_by_id"))
    def test_missing_row_field(self, field):
        with allure.step("Удалить обязательное nullable-поле результата"):
            snapshot = tv.snapshot()
            snapshot["results"][0].pop(field)
        with allure.step("Проверить неполный контракт"):
            result = verification.evaluate_snapshot(
                snapshot, _expected(), launch_id=tv.LAUNCH_ID,
                project_id=tv.PROJECT_ID)
            assert result.verdict == verification.VERDICT_INCONCLUSIVE

    @allure.title("Без totals и прочитанных страниц полный набор не доказан")
    @pytest.mark.parametrize("pagination", tv.UNPROVEN_PAGINATION)
    def test_unproven_page_count(self, pagination):
        with allure.step("Подставить неполные метаданные пагинации"):
            snapshot = tv.snapshot()
            snapshot["pagination"] = pagination
        with allure.step("Не подтверждать даже совпадающие строки"):
            result = verification.evaluate_snapshot(
                snapshot, _expected(), launch_id=tv.LAUNCH_ID,
                project_id=tv.PROJECT_ID)
            assert result.verdict == verification.VERDICT_INCONCLUSIVE

    @allure.title("Переданный ID не подменяет отсутствующую записанную привязку launch")
    def test_unrecorded_launch_requires_adoption(self, tmp_path):
        with allure.step("Подготовить state без записанного launch"):
            state_dir = _write_state(tmp_path, launch=None)
            probe = FakeProbe(tv.snapshot())
        with allure.step("Проверить блокировку до probe"):
            result = _verify(state_dir, probe, launch_id=tv.LAUNCH_ID)
            assert result.confirmed is False
            assert probe.calls == []
            assert _read(state_dir)["upload"]["status"] == "sent"
