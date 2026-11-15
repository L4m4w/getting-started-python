import copy
import json
from pathlib import Path

import allure
import pytest

from infrastructure.reporting.testops import client, lifecycle, state as state_mod
from test_data.consts.testops_lifecycle import (
    BOUND_IDS, DEAD_PID, ENDPOINT, EXECUTION_ID, FAILED_CODE,
    LAUNCH_EMPTY, LAUNCH_ID, LAUNCH_MATCHING, LAUNCH_NAME, LAUNCH_NO_STATS,
    LAUNCH_OVERDELIVERED, LAUNCH_PARTIAL, LAUNCH_WRONG_ID,
    LAUNCH_WRONG_PROJECT, PROJECT_ID, RESULTS_MATCHING_BIND,
    RESULTS_WRONG_CASE, SCENARIO_IDS, SCENARIO_STATUSES,
)


def _scenarios(bound=True):
    scenarios = {}
    for index, scenario_id in enumerate(SCENARIO_IDS):
        scenarios[scenario_id] = {
            "uuid": f"uuid-{index}-{scenario_id}",
            "status": SCENARIO_STATUSES[scenario_id],
            "testops_id": BOUND_IDS[scenario_id] if bound else None,
            "binding": "bound" if bound else "unresolved",
            "binding_source": "assign" if bound else None,
        }
    return scenarios


def _package_dir(tmp_path):
    directory = tmp_path / "pkg"
    directory.mkdir(exist_ok=True)
    (directory / "one-result.json").write_text("{}", encoding="utf-8")
    return directory


def _write_state(tmp_path, upload=None, launch=None, scenarios=None):
    state_dir = tmp_path / "testops" / EXECUTION_ID
    state_dir.mkdir(parents=True)
    state = state_mod.new_state(EXECUTION_ID, ENDPOINT, PROJECT_ID)
    state["scenarios"] = scenarios if scenarios is not None else _scenarios()
    state["package"] = {"dir": str(_package_dir(tmp_path)),
                        "sha256": "f" * 64, "files": 1,
                        "results": len(state["scenarios"]),
                        "mode": "bind", "built_at": "2026-01-01T00:00:00+00:00"}
    if launch is not None:
        state["launch"] = launch
    if upload:
        state["upload"].update(upload)
    state_mod.save_state(state_dir, state)
    return state_dir


def _persist(state_dir):
    snapshots = []

    def save(state):
        snapshots.append(copy.deepcopy(state))
        state_mod.save_state(state_dir, state)
    return save, snapshots


def _read(state_dir):
    return json.loads((Path(state_dir) / "state.json").read_text())


class FakeTransport:
    """Подмена сетевого транспорта: фиксированные CommandResult/списки/сбои."""

    def __init__(self, **operations):
        self.operations = operations
        self.calls = []

    def _do(self, operation, *args):
        self.calls.append((operation, args))
        action = self.operations.get(operation)
        if callable(action):
            return action(*args)
        if isinstance(action, BaseException):
            raise action
        return action

    def create_launch(self, *args):
        return self._do("create_launch", *args)

    def upload_package(self, *args):
        return self._do("upload_package", *args)

    def get_launch(self, *args):
        return self._do("get_launch", *args)

    def list_launches(self, *args):
        return self._do("list_launches", *args)

    def list_cases(self, *args):
        return self._do("list_cases", *args)

    def list_launch_results(self, *args):
        return self._do("list_launch_results", *args)


def _ok(payload):
    return client.CommandResult(0, json.dumps(payload), "")


def _v1_state(upload_status="pending", launch=None):
    """Минимальный schema-1 state в форме artifacts/testops из handoff 11."""
    return {
        "schema_version": 1,
        "execution_id": EXECUTION_ID,
        "endpoint": ENDPOINT,
        "project_id": PROJECT_ID,
        "updated_at": "2026-11-14T15:10:25+00:00",
        "results": {"path": "x", "sha256": "a" * 64, "files": 3,
                    "results": 3},
        "scenarios": _scenarios(),
        "unmapped": [],
        "package": {"dir": "/tmp/pkg", "sha256": "b" * 64, "files": 3,
                    "results": 3, "mode": "bind",
                    "built_at": "2026-11-14T15:10:25+00:00"},
        "launch": launch,
        "upload": {"status": upload_status, "attempts": 2,
                   "started_at": "2026-11-14T15:11:00+00:00",
                   "finished_at": "2026-11-14T15:12:00+00:00",
                   "exit_code": FAILED_CODE, "package_sha256": "b" * 64,
                   "log": "upload.log"},
    }


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Целостность состояния и миграция schema 1")
@allure.severity(allure.severity_level.NORMAL)
class TestStateIntegrity:

    @allure.title("Повреждённый state.json блокирует загрузку без потери истории")
    def test_corrupt_state_raises_and_never_starts_fresh(self, tmp_path):
        with allure.step("Записать битый JSON и JSON не-объект"):
            state_dir = tmp_path / "testops" / EXECUTION_ID
            state_dir.mkdir(parents=True)
            path = Path(state_dir) / "state.json"
            path.write_text("{not json", encoding="utf-8")
        with allure.step("Проверить явную блокировку и сохранность файла"):
            with pytest.raises(state_mod.StateCorruptError):
                state_mod.load_state(state_dir)
            with pytest.raises(state_mod.StateCorruptError):
                lifecycle.perform_upload(
                    state_dir, FakeTransport(), launch_name=LAUNCH_NAME)
            assert path.read_text(encoding="utf-8") == "{not json"
            path.write_text("[1, 2]", encoding="utf-8")
            with pytest.raises(state_mod.StateCorruptError):
                state_mod.load_state(state_dir)

    @allure.title("Неподдерживаемая версия схемы отклоняется явно")
    def test_unsupported_schema_is_blocked(self, tmp_path):
        with allure.step("Записать состояние с schema_version=99"):
            state_dir = tmp_path / "testops" / EXECUTION_ID
            state_dir.mkdir(parents=True)
            payload = _v1_state()
            payload["schema_version"] = 99
            (Path(state_dir) / "state.json").write_text(
                json.dumps(payload), encoding="utf-8")
        with allure.step("Проверить StateSchemaError"):
            with pytest.raises(state_mod.StateSchemaError):
                state_mod.load_state(state_dir)

    @allure.title("Schema 1 мигрирует в память: failed с launch становится unknown")
    def test_schema1_failed_with_launch_migrates_to_unknown(self, tmp_path):
        with allure.step("Сохранить v1-состояние failed с записанным launch"):
            state_dir = tmp_path / "testops" / EXECUTION_ID
            state_dir.mkdir(parents=True)
            launch = {"id": LAUNCH_ID, "name": LAUNCH_NAME,
                      "url": f"{ENDPOINT}/launch/{LAUNCH_ID}",
                      "created_at": "2026-11-14T15:11:00+00:00"}
            (Path(state_dir) / "state.json").write_text(
                json.dumps(_v1_state("failed", launch)), encoding="utf-8")
        with allure.step("Загрузить и проверить миграцию без потери данных"):
            state = state_mod.load_state(state_dir)
        with allure.step("Проверить schema 2, unknown и сохранённые данные"):
            assert state["schema_version"] == 2
            assert state["upload"]["status"] == "unknown"
            assert state["upload"]["attempts"] == 2
            assert state["launch"]["id"] == LAUNCH_ID
            assert state["scenarios"]["CAT-UPD-VAL-001"]["testops_id"] == \
                BOUND_IDS["CAT-UPD-VAL-001"]

    @allure.title("Операторские переходы: resolve/adopt/abandon под контролем")
    def test_operator_recovery_transitions(self, tmp_path):
        with allure.step("Снять stale in_progress явным разрешением"):
            state_dir = _write_state(
                tmp_path, upload={"status": "in_progress", "attempts": 1})
            state = state_mod.load_state(state_dir)
            state_mod.resolve_in_progress(state, "process died mid-upload")
        with allure.step("Принять найденный вручную launch и проверить статус"):
            state_mod.adopt_launch(state, LAUNCH_ID, LAUNCH_NAME,
                                   f"{ENDPOINT}/launch/{LAUNCH_ID}")
            with pytest.raises(ValueError):
                state_mod.adopt_launch(state, LAUNCH_ID + 1)
            assert state["upload"]["status"] == "unknown"
            assert state["launch"]["id"] == LAUNCH_ID
            assert state["launch"]["source"] == "adopted"
        with allure.step("Отказаться от launch: запись уходит в аудит"):
            state_mod.abandon_launch(state, "operator deleted the orphan")
            assert state["launch"] is None
            assert state["upload"]["status"] == "failed"
            abandoned = state["upload"]["abandoned"]
            assert abandoned[0]["id"] == LAUNCH_ID
            assert "orphan" in abandoned[0]["reason"]

    @allure.title("Schema 1: uploaded и unknown сохраняются, failed становится unknown")
    def test_schema1_terminal_statuses_survive_migration(self, tmp_path):
        with allure.step("Промигрировать uploaded, unknown и чистый failed"):
            for status in ("uploaded", "unknown", "failed"):
                state_dir = tmp_path / status
                state_dir.mkdir()
                (state_dir / "state.json").write_text(
                    json.dumps(_v1_state(status)), encoding="utf-8")
                migrated = state_mod.load_state(state_dir)
                assert migrated["upload"]["status"] == ("unknown" if status == "failed" else status)
        with allure.step("Проверить пометку мигрированного uploaded"):
            migrated = state_mod.load_state(tmp_path / "uploaded")
            assert migrated["upload"]["confirmation"]["method"] == "migrated"


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Execution lock")
@allure.severity(allure.severity_level.NORMAL)
class TestExecutionLock:

    @allure.title("Второй одновременный захват получает понятный отказ")
    def test_second_holder_is_refused(self, tmp_path):
        with allure.step("Захватить lock и попытаться захватить повторно"):
            state_dir = tmp_path / "testops" / EXECUTION_ID
            first = lifecycle.ExecutionLock(state_dir, "upload")
            first.acquire()
            second = lifecycle.ExecutionLock(state_dir, "upload")
            with pytest.raises(lifecycle.LockHeldError):
                second.acquire()
            first.release()
        with allure.step("Проверить, что после release захват снова возможен"):
            third = lifecycle.ExecutionLock(state_dir, "verify")
            third.acquire()
            third.release()
            assert not (Path(state_dir) / "execution.lock").exists()

    @allure.title("Блокировка мёртвого pid забирается, но in_progress всё равно блокирует")
    def test_stale_lock_reclaimed_without_bypassing_state(self, tmp_path):
        with allure.step("Создать lock мёртвого процесса и состояние in_progress"):
            state_dir = _write_state(
                tmp_path, upload={"status": "in_progress", "attempts": 1})
            lock_path = Path(state_dir) / "execution.lock"
            lock_path.write_text(json.dumps(
                {"pid": DEAD_PID, "token": "dead", "operation": "upload",
                 "acquired_at": "2026-01-01T00:00:00+00:00"}),
                encoding="utf-8")
        with allure.step("Выполнить upload: lock забирается, статус блокирует"):
            run = lifecycle.perform_upload(
                state_dir, FakeTransport(), launch_name=LAUNCH_NAME)
        with allure.step("Проверить блокировку и отсутствие внешних вызовов"):
            assert run.outcome == lifecycle.OUTCOME_BLOCKED
            assert "in_progress" in run.message
            assert not lock_path.exists()

    @allure.title("Повреждённый lock-файл отклоняется с понятной диагностикой")
    def test_corrupt_lock_is_refused(self, tmp_path):
        with allure.step("Записать мусор в execution.lock"):
            state_dir = tmp_path / "testops" / EXECUTION_ID
            state_dir.mkdir(parents=True)
            (state_dir / "execution.lock").write_text(
                "garbage", encoding="utf-8")
        with allure.step("Проверить отказ захвата"):
            with pytest.raises(lifecycle.LockHeldError):
                lifecycle.ExecutionLock(state_dir).acquire()


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Оркестрация upload")
@allure.severity(allure.severity_level.NORMAL)
class TestUploadLifecycle:

    @allure.title("in_progress сохраняется до первого внешнего вызова")
    def test_in_progress_is_durable_before_external_write(self, tmp_path):
        with allure.step("Подменить persist записью снимков и успешный ответ"):
            state_dir = _write_state(tmp_path)
            persist, snapshots = _persist(state_dir)
            transport = FakeTransport(
                create_launch=_ok({"id": LAUNCH_ID}),
                upload_package=client.CommandResult(0, "done", ""))
        with allure.step("Выполнить upload"):
            lifecycle.perform_upload(
                state_dir, transport, launch_name=LAUNCH_NAME,
                persist=persist)
        with allure.step("Проверить порядок: in_progress сохранён до вызова"):
            assert snapshots[0]["upload"]["status"] == "in_progress"
            assert transport.calls[0][0] == "create_launch"
            assert snapshots[1]["upload"]["phase"] == "launch_create"
            assert snapshots[-1]["upload"]["status"] == "sent"

    @allure.title("Успешная отправка даёт sent, verify с полным доказательством — uploaded")
    def test_happy_path_sent_then_confirmed(self, tmp_path):
        with allure.step("Выполнить upload с успешным create и upload"):
            state_dir = _write_state(tmp_path)
            transport = FakeTransport(
                create_launch=_ok({"id": LAUNCH_ID}),
                upload_package=client.CommandResult(0, "done", ""),
                get_launch=_ok(LAUNCH_MATCHING),
                list_launch_results=lambda *a: RESULTS_MATCHING_BIND)
            upload = lifecycle.perform_upload(
                state_dir, transport, launch_name=LAUNCH_NAME)
        with allure.step("Проверить sent и записанный launch"):
            assert upload.outcome == lifecycle.OUTCOME_SENT
            assert upload.state["upload"]["status"] == "sent"
            assert upload.state["launch"]["id"] == LAUNCH_ID
        with allure.step("Выполнить verify с полным серверным доказательством"):
            verification = lifecycle.perform_verify(state_dir, transport)
            state = _read(state_dir)
        with allure.step("Проверить uploaded и повторный блок"):
            assert verification.verdict == lifecycle.VERDICT_CONFIRMED
            assert state["upload"]["status"] == "uploaded"
            repeat = lifecycle.perform_upload(
                state_dir, transport, launch_name=LAUNCH_NAME, retry=True)
            assert repeat.outcome == lifecycle.OUTCOME_BLOCKED

    @allure.title("sent не даёт слепого повтора: повторная отправка заблокирована")
    def test_sent_blocks_resend(self, tmp_path):
        with allure.step("Записать состояние sent с launch"):
            state_dir = _write_state(
                tmp_path, upload={"status": "sent", "attempts": 1},
                launch={"id": LAUNCH_ID, "name": LAUNCH_NAME,
                        "url": f"{ENDPOINT}/launch/{LAUNCH_ID}",
                        "created_at": "t"})
            transport = FakeTransport()
        with allure.step("Попытаться повторить upload с retry"):
            run = lifecycle.perform_upload(
                state_dir, transport, launch_name=LAUNCH_NAME, retry=True)
        with allure.step("Проверить блок и отсутствие внешних вызовов"):
            assert run.outcome == lifecycle.OUTCOME_BLOCKED
            assert transport.calls == []

    @allure.title("Timeout на launch create фиксирует unknown")
    def test_timeout_at_launch_create_is_unknown(self, tmp_path):
        with allure.step("Подменить create timeout-ответом"):
            state_dir = _write_state(tmp_path)
            transport = FakeTransport(
                create_launch=client.CommandResult(
                    None, "", "", "timeout"))
        with allure.step("Выполнить upload и проверить unknown без launch"):
            run = lifecycle.perform_upload(
                state_dir, transport, launch_name=LAUNCH_NAME)
            assert run.outcome == lifecycle.OUTCOME_UNKNOWN
            assert run.state["upload"]["status"] == "unknown"
            assert run.state["upload"]["phase"] == "launch_create"
            assert run.state["launch"] is None

    @allure.title("Timeout на upload фиксирует unknown и сохраняет launch")
    def test_timeout_at_upload_is_unknown_launch_kept(self, tmp_path):
        with allure.step("create успешен, upload — timeout"):
            state_dir = _write_state(tmp_path)
            transport = FakeTransport(
                create_launch=_ok({"id": LAUNCH_ID}),
                upload_package=client.CommandResult(
                    None, "", "", "timeout"))
            run = lifecycle.perform_upload(
                state_dir, transport, launch_name=LAUNCH_NAME)
        with allure.step("Проверить unknown, сохранённый launch и блок retry"):
            assert run.outcome == lifecycle.OUTCOME_UNKNOWN
            assert run.state["launch"]["id"] == LAUNCH_ID
            assert run.state["upload"]["phase"] == "upload"
            retry = lifecycle.perform_upload(
                state_dir, transport, launch_name=LAUNCH_NAME, retry=True)
            assert retry.outcome == lifecycle.OUTCOME_BLOCKED
            assert [c[0] for c in transport.calls].count("create_launch") == 1

    @allure.title("Прерывание на create и на upload фиксирует unknown без повтора")
    def test_interruption_marks_unknown(self, tmp_path):
        with allure.step("Прервать create и проверить unknown"):
            create_dir = _write_state(tmp_path / "a")
            transport = FakeTransport(create_launch=KeyboardInterrupt())
            run = lifecycle.perform_upload(
                create_dir, transport, launch_name=LAUNCH_NAME)
            assert run.outcome == lifecycle.OUTCOME_INTERRUPTED
            assert run.state["upload"]["status"] == "unknown"
        with allure.step("Прервать upload и проверить сохранённый launch"):
            upload_dir = _write_state(tmp_path / "b")
            transport = FakeTransport(
                create_launch=_ok({"id": LAUNCH_ID}),
                upload_package=KeyboardInterrupt())
            run = lifecycle.perform_upload(
                upload_dir, transport, launch_name=LAUNCH_NAME)
            assert run.outcome == lifecycle.OUTCOME_INTERRUPTED
            assert run.state["upload"]["status"] == "unknown"
            assert run.state["launch"]["id"] == LAUNCH_ID

    @allure.title("Ненулевой exit upload — unknown с возможным частичным принятием")
    def test_nonzero_upload_exit_is_unknown_and_blocks_retry(self, tmp_path):
        with allure.step("create успешен, upload завершается exit 4"):
            state_dir = _write_state(tmp_path)
            transport = FakeTransport(
                create_launch=_ok({"id": LAUNCH_ID}),
                upload_package=client.CommandResult(
                    FAILED_CODE, "", "partial write"))
            run = lifecycle.perform_upload(
                state_dir, transport, launch_name=LAUNCH_NAME)
        with allure.step("Проверить unknown и блок повтора даже с retry"):
            assert run.outcome == lifecycle.OUTCOME_UNKNOWN
            assert run.state["upload"]["status"] == "unknown"
            assert run.state["launch"]["id"] == LAUNCH_ID
            retry = lifecycle.perform_upload(
                state_dir, transport, launch_name=LAUNCH_NAME, retry=True)
            assert retry.outcome == lifecycle.OUTCOME_BLOCKED
            assert [c[0] for c in transport.calls].count(
                "create_launch") == 1

    @allure.title("Create exit 0 с нечитаемым ID — unknown; повтор не создаёт второй launch")
    def test_unreadable_launch_id_is_unknown_no_new_launch(self, tmp_path):
        with allure.step("create возвращает stdout без распознаваемого id"):
            state_dir = _write_state(tmp_path)
            transport = FakeTransport(
                create_launch=client.CommandResult(0, "Launch created", ""))
            run = lifecycle.perform_upload(
                state_dir, transport, launch_name=LAUNCH_NAME)
        with allure.step("Проверить unknown и запрет повторного create"):
            assert run.outcome == lifecycle.OUTCOME_UNKNOWN
            assert run.state["launch"] is None
            retry = lifecycle.perform_upload(
                state_dir, transport, launch_name=LAUNCH_NAME, retry=True)
            assert retry.outcome == lifecycle.OUTCOME_BLOCKED
            assert [c[0] for c in transport.calls] == ["create_launch"]

    @allure.title("Retry после доказанного failed использует записанный launch")
    def test_failed_retry_reuses_recorded_launch(self, tmp_path):
        with allure.step("Состояние failed с launch после launch_error upload"):
            state_dir = _write_state(
                tmp_path,
                upload={"status": "failed", "attempts": 1,
                        "phase": "upload"},
                launch={"id": LAUNCH_ID, "name": LAUNCH_NAME,
                        "url": f"{ENDPOINT}/launch/{LAUNCH_ID}",
                        "created_at": "t"})
            transport = FakeTransport(
                upload_package=client.CommandResult(0, "done", ""))
        with allure.step("Выполнить retry"):
            run = lifecycle.perform_upload(
                state_dir, transport, launch_name=LAUNCH_NAME, retry=True)
        with allure.step("Проверить reuse launch без нового create"):
            assert run.outcome == lifecycle.OUTCOME_SENT
            assert [c[0] for c in transport.calls] == ["upload_package"]
            assert transport.calls[0][1][2] == LAUNCH_ID
            assert run.state["launch"]["id"] == LAUNCH_ID

    @allure.title("launch_error транспорта — доказанный failed до внешней записи")
    def test_launch_error_is_proven_failure(self, tmp_path):
        with allure.step("Подменить create ошибкой запуска процесса"):
            state_dir = _write_state(tmp_path)
            transport = FakeTransport(
                create_launch=client.CommandResult(
                    None, "", "", "launch_error"))
            run = lifecycle.perform_upload(
                state_dir, transport, launch_name=LAUNCH_NAME)
        with allure.step("Проверить failed и возможность retry"):
            assert run.outcome == lifecycle.OUTCOME_FAILED
            assert run.state["upload"]["status"] == "failed"
            assert run.state["launch"] is None

    @allure.title("uploaded, unknown и in_progress блокируют новые попытки")
    def test_terminal_and_indeterminate_statuses_block(self, tmp_path):
        with allure.step("Проверить блок для каждого неопределённого статуса"):
            for index, status in enumerate(
                    ("uploaded", "unknown", "in_progress")):
                state_dir = _write_state(
                    tmp_path / f"s{index}",
                    upload={"status": status, "attempts": 1})
                transport = FakeTransport()
                run = lifecycle.perform_upload(
                    state_dir, transport, launch_name=LAUNCH_NAME,
                    retry=True)
                assert run.outcome == lifecycle.OUTCOME_BLOCKED
                assert transport.calls == []


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("Верификация upload")
@allure.severity(allure.severity_level.NORMAL)
class TestVerifyLifecycle:

    def _sent(self, tmp_path):
        return _write_state(
            tmp_path, upload={"status": "sent", "attempts": 1},
            launch={"id": LAUNCH_ID, "name": LAUNCH_NAME,
                    "url": f"{ENDPOINT}/launch/{LAUNCH_ID}",
                    "created_at": "t"})

    @allure.title("Нулевая статистика не разрешает повтор во время обработки")
    def test_empty_launch_does_not_confirm(self, tmp_path):
        with allure.step("verify читает launch со статистикой 0"):
            state_dir = self._sent(tmp_path)
            transport = FakeTransport(
                get_launch=_ok(LAUNCH_EMPTY),
                list_launch_results=lambda *a: [])
            verification = lifecycle.perform_verify(state_dir, transport)
            state = _read(state_dir)
        with allure.step("Проверить сохранение sent и запрет retry"):
            assert verification.verdict == lifecycle.VERDICT_EMPTY
            assert state["upload"]["status"] == "sent"
            retry = lifecycle.perform_upload(
                state_dir, FakeTransport(
                    upload_package=client.CommandResult(0, "done", "")),
                launch_name=LAUNCH_NAME, retry=True)
            assert retry.outcome == lifecycle.OUTCOME_BLOCKED
            assert retry.launch_id == LAUNCH_ID

    @allure.title("Неверный ID или проект launch не подтверждает upload")
    def test_wrong_launch_or_project_is_contradiction(self, tmp_path):
        with allure.step("verify: launch get вернул другой проект"):
            state_dir = self._sent(tmp_path / "p")
            transport = FakeTransport(
                get_launch=_ok(LAUNCH_WRONG_PROJECT),
                list_launch_results=lambda *a: RESULTS_MATCHING_BIND)
            verification = lifecycle.perform_verify(state_dir, transport)
        with allure.step("Проверить contradiction и отсутствие uploaded"):
            assert verification.verdict == lifecycle.VERDICT_CONTRADICTION
            assert verification.state["upload"]["status"] == "unknown"
            assert verification.state["launch"]["id"] == LAUNCH_ID
        with allure.step("verify: launch get вернул чужой id"):
            state_dir = self._sent(tmp_path / "i")
            transport = FakeTransport(get_launch=_ok(LAUNCH_WRONG_ID))
            verification = lifecycle.perform_verify(state_dir, transport)
            assert verification.verdict == lifecycle.VERDICT_MISSING
            assert verification.state["upload"]["status"] == "unknown"

    @allure.title("Частичный набор результатов оставляет outcome неопределённым")
    def test_partial_result_set_stays_unconfirmed(self, tmp_path):
        with allure.step("verify читает статистику меньше ожидаемой"):
            state_dir = self._sent(tmp_path)
            transport = FakeTransport(
                get_launch=_ok(LAUNCH_PARTIAL),
                list_launch_results=lambda *a: RESULTS_MATCHING_BIND[:1])
            verification = lifecycle.perform_verify(state_dir, transport)
        with allure.step("Проверить partial и сохранённый статус sent"):
            assert verification.verdict == lifecycle.VERDICT_PARTIAL
            assert verification.state["upload"]["status"] == "sent"
            assert verification.confirmed is False

    @allure.title("Совпадение без чтения per-result не подтверждает bindings")
    def test_match_without_result_probe_is_inconclusive(self, tmp_path):
        with allure.step("verify: статистика совпадает, probe отсутствует"):
            state_dir = self._sent(tmp_path)
            transport = FakeTransport(get_launch=_ok(LAUNCH_MATCHING))
            transport.list_launch_results = None
            verification = lifecycle.perform_verify(state_dir, transport)
        with allure.step("Проверить inconclusive и статус sent"):
            assert verification.verdict == lifecycle.VERDICT_INCONCLUSIVE
            assert verification.checks["bindings"] == "inconclusive"
            assert verification.state["upload"]["status"] == "sent"

    @allure.title("Несоответствие per-result привязок — contradiction")
    def test_binding_mismatch_is_contradiction(self, tmp_path):
        with allure.step("verify: результаты привязаны к чужим кейсам"):
            state_dir = self._sent(tmp_path)
            transport = FakeTransport(
                get_launch=_ok(LAUNCH_MATCHING),
                list_launch_results=lambda *a: RESULTS_WRONG_CASE)
            verification = lifecycle.perform_verify(state_dir, transport)
        with allure.step("Проверить contradiction и unknown"):
            assert verification.verdict == lifecycle.VERDICT_CONTRADICTION
            assert verification.state["upload"]["status"] == "unknown"

    @allure.title("Переполненная статистика launch — contradiction")
    def test_overdelivered_stats_are_contradiction(self, tmp_path):
        with allure.step("verify: результатов больше ожидаемого"):
            state_dir = self._sent(tmp_path)
            transport = FakeTransport(
                get_launch=_ok(LAUNCH_OVERDELIVERED),
                list_launch_results=lambda *a: RESULTS_MATCHING_BIND)
            verification = lifecycle.perform_verify(state_dir, transport)
        with allure.step("Проверить contradiction"):
            assert verification.verdict == lifecycle.VERDICT_CONTRADICTION
            assert verification.state["upload"]["status"] == "unknown"

    @allure.title("Нечитаемая статистика launch — inconclusive без понижения")
    def test_unreadable_stats_are_inconclusive(self, tmp_path):
        with allure.step("verify: ответ без распознаваемой статистики"):
            state_dir = self._sent(tmp_path)
            transport = FakeTransport(
                get_launch=_ok(LAUNCH_NO_STATS),
                list_launch_results=lambda *a: RESULTS_MATCHING_BIND)
            verification = lifecycle.perform_verify(state_dir, transport)
        with allure.step("Проверить inconclusive и сохранённый sent"):
            assert verification.verdict == lifecycle.VERDICT_INCONCLUSIVE
            assert verification.checks["result_set"] == "inconclusive"
            assert verification.state["upload"]["status"] == "sent"

    @allure.title("Сбой чтения launch — unreachable без изменения состояния")
    def test_unreachable_launch_keeps_state(self, tmp_path):
        with allure.step("verify: launch get падает с ошибкой сети"):
            state_dir = self._sent(tmp_path)
            transport = FakeTransport(
                get_launch=client.CommandResult(None, "", "", "timeout"))
            verification = lifecycle.perform_verify(state_dir, transport)
        with allure.step("Проверить unreachable и неизменный sent"):
            assert verification.verdict == lifecycle.VERDICT_UNREACHABLE
            assert verification.state["upload"]["status"] == "sent"
