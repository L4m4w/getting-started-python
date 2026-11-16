import json

import allure
import pytest

from infrastructure.http.client import HttpResponse, PreparationError
from infrastructure.reporting.testops import rest
from test_data.consts import testops_rest as c


class UnexpectedRoute(BaseException):
    """Маршрут не объявлен: ошибка фикстуры, а не поведение probe."""


class FakeHttp:
    """Подмена HTTP-слоя: маршрут → ответ/исключение, без сети и без env."""

    def __init__(self, routes=None):
        self.routes = dict(routes or {})
        self.calls = []

    def request(self, endpoint, method, path, *, headers=None, form=None):
        self.calls.append({"endpoint": endpoint, "method": method,
                           "path": path, "headers": dict(headers or {}),
                           "form": dict(form or {})})
        action = self.routes.get((method, path))
        if action is None:
            raise UnexpectedRoute(f"unexpected request: {method} {path}")
        if isinstance(action, (list, tuple)):
            queue = list(action)
            action = queue.pop(0)
            if queue:
                self.routes[(method, path)] = queue
        if isinstance(action, BaseException):
            raise action
        return action


def _resp(status, payload):
    body = payload if isinstance(payload, str) else json.dumps(payload)
    return HttpResponse(status, body.encode("utf-8"), None)


def _routes(overrides=None):
    routes = {
        ("POST", c.TOKEN_PATH): _resp(200, c.TOKEN_OK),
        ("GET", c.LAUNCH_PATH): _resp(200, c.LAUNCH),
        ("GET", c.PROGRESS_PATH): _resp(200, c.PROGRESS_READY),
        ("GET", c.STATISTIC_PATH): _resp(200, c.STATISTIC),
        ("GET", c.results_path(0)): _resp(200, c.PAGE0_FULL),
        ("GET", c.results_path(1)): _resp(200, c.PAGE1_LAST),
    }
    routes.update(overrides or {})
    return routes


def _probe(http, **kwargs):
    return rest.RestProbe(c.API_TOKEN, http=http,
                          page_size=c.PAGE_SIZE, max_pages=c.MAX_PAGES,
                          **kwargs)


def _paths(http):
    return [(call["method"], call["path"]) for call in http.calls]


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("REST probe: безопасная конструкция")
@allure.severity(allure.severity_level.NORMAL)
class TestProbeConstruction:

    @allure.title("Создание probe не выполняет ни одного HTTP-вызова")
    def test_construction_is_io_free(self):
        with allure.step("Создать probe с подменённым HTTP-слоем"):
            http = FakeHttp()
            _probe(http)
        with allure.step("Проверить отсутствие вызовов"):
            assert http.calls == []

    @allure.title("Пустой токен и невалидный HTTP-слой отклоняются")
    def test_invalid_arguments_are_rejected(self):
        with allure.step("Проверить ValueError на пустой токен и плохой http"):
            with pytest.raises(ValueError):
                rest.RestProbe("")
            with pytest.raises(ValueError):
                rest.RestProbe(c.API_TOKEN, http=object())
            with pytest.raises(ValueError):
                rest.RestProbe(c.API_TOKEN, http=FakeHttp(), page_size=0)

    @allure.title("Нечисловой launch_id возвращает inconclusive без HTTP")
    def test_invalid_launch_id_is_inconclusive(self):
        with allure.step("Вызвать read_snapshot с нечисловым id"):
            http = FakeHttp()
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, "n/a")
        with allure.step("Проверить inconclusive и отсутствие вызовов"):
            assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE
            assert http.calls == []


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("REST probe: обмен токена и секреты")
@allure.severity(allure.severity_level.NORMAL)
class TestAuthentication:

    @allure.title("Успешный обмен: токен только в форме, JWT только в памяти")
    def test_token_exchange_and_secret_hygiene(self):
        with allure.step("Выполнить полный снимок"):
            http = FakeHttp(_routes())
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить complete и порядок вызовов"):
            assert snapshot["outcome"] == rest.OUTCOME_COMPLETE
            assert _paths(http)[0] == ("POST", c.TOKEN_PATH)
        with allure.step("Проверить форму обмена и заголовки GET-вызовов"):
            auth_call = http.calls[0]
            assert auth_call["form"] == {
                "grant_type": "apitoken", "scope": "openid",
                "token": c.API_TOKEN}
            assert all(c.API_TOKEN not in value
                       for value in auth_call["headers"].values())
            for call in http.calls[1:]:
                assert call["headers"]["Authorization"] == \
                    f"Bearer {c.JWT}"
        with allure.step("Проверить, что секреты не попали в snapshot"):
            rendered = json.dumps(snapshot)
            assert c.API_TOKEN not in rendered
            assert c.JWT not in rendered

    @allure.title("401 на обмене токена — unreachable, дальше запросов нет")
    def test_auth_401_is_unreachable(self):
        with allure.step("Подменить обмен ответом 401"):
            http = FakeHttp(_routes(
                {("POST", c.TOKEN_PATH): _resp(401, {"error": "x"})}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить unreachable и единственный вызов"):
            assert snapshot["outcome"] == rest.OUTCOME_UNREACHABLE
            assert snapshot["launch"] is None
            assert _paths(http) == [("POST", c.TOKEN_PATH)]
            assert c.API_TOKEN not in json.dumps(snapshot)

    @allure.title("Ответ обмена без access_token — inconclusive")
    def test_auth_bad_schema_is_inconclusive(self):
        with allure.step("Подменить обмен ответом без access_token"):
            http = FakeHttp(_routes(
                {("POST", c.TOKEN_PATH): _resp(200, c.TOKEN_NO_ACCESS)}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить inconclusive без GET-вызовов"):
            assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE
            assert _paths(http) == [("POST", c.TOKEN_PATH)]

    @allure.title("Неподдерживаемый token_type — inconclusive")
    def test_auth_wrong_token_type_is_inconclusive(self):
        with allure.step("Подменить обмен ответом с token_type=mac"):
            http = FakeHttp(_routes(
                {("POST", c.TOKEN_PATH): _resp(200, c.TOKEN_WRONG_TYPE)}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить inconclusive"):
            assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("REST probe: чтение launch")
@allure.severity(allure.severity_level.NORMAL)
class TestLaunchRead:

    @allure.title("404 на прямом GET launch — единственный источник missing")
    def test_launch_404_is_missing(self):
        with allure.step("Подменить launch get ответом 404"):
            http = FakeHttp(_routes(
                {("GET", c.LAUNCH_PATH): _resp(404, {"status": 404})}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить missing и остановку обхода"):
            assert snapshot["outcome"] == rest.OUTCOME_MISSING
            assert snapshot["launch"] is None
            assert _paths(http) == [("POST", c.TOKEN_PATH),
                                    ("GET", c.LAUNCH_PATH)]

    @allure.title("403 на прямом GET launch — unreachable, не missing")
    def test_launch_403_is_unreachable(self):
        with allure.step("Подменить launch get ответом 403"):
            http = FakeHttp(_routes(
                {("GET", c.LAUNCH_PATH): _resp(403, "")}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить unreachable"):
            assert snapshot["outcome"] == rest.OUTCOME_UNREACHABLE

    @allure.title("LaunchDto без closed/projectId — inconclusive без подстановки")
    def test_launch_missing_fields_are_inconclusive(self):
        with allure.step("Подменить launch ответами без обязательных полей"):
            for bad in (c.LAUNCH_NO_CLOSED, c.LAUNCH_NO_PROJECT):
                http = FakeHttp(_routes(
                    {("GET", c.LAUNCH_PATH): _resp(200, bad)}))
                snapshot = _probe(http).read_snapshot(
                    c.ENDPOINT, c.LAUNCH_ID)
                assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE
                assert snapshot["launch"] is None

    @allure.title("Чужой id в ответе launch — inconclusive")
    def test_launch_wrong_id_is_inconclusive(self):
        with allure.step("Подменить launch ответом с другим id"):
            http = FakeHttp(_routes(
                {("GET", c.LAUNCH_PATH): _resp(200, c.LAUNCH_WRONG_ID)}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить inconclusive"):
            assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE

    @allure.title("Невалидный JSON launch — inconclusive")
    def test_launch_invalid_json_is_inconclusive(self):
        with allure.step("Подменить launch битым телом"):
            http = FakeHttp(_routes(
                {("GET", c.LAUNCH_PATH): _resp(200, "{not json")}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить inconclusive"):
            assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("REST probe: progress и statistic")
@allure.severity(allure.severity_level.NORMAL)
class TestProgressAndStatistic:

    @allure.title("ready=false и closed=false — полный прочитанный снимок")
    def test_unprocessed_launch_is_still_complete(self):
        with allure.step("Подменить открытый launch и ready=false"):
            http = FakeHttp(_routes(
                {("GET", c.LAUNCH_PATH): _resp(200, c.LAUNCH_OPEN),
                 ("GET", c.PROGRESS_PATH): _resp(200, c.PROGRESS_NOT_READY)}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить complete с сохранёнными флагами"):
            assert snapshot["outcome"] == rest.OUTCOME_COMPLETE
            assert snapshot["ready"] is False
            assert snapshot["launch"]["closed"] is False

    @allure.title("TestStatusCount[] сводится в counts без потери in_progress")
    def test_statistic_array_becomes_counts(self):
        with allure.step("Выполнить снимок со статистикой из констант"):
            http = FakeHttp(_routes())
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить словарь статусов"):
            assert snapshot["stats"] == c.EXPECTED_STATS
            assert snapshot["outcome"] == rest.OUTCOME_COMPLETE

    @allure.title("Статистика не-массив, дубликат и отрицательный count — inconclusive")
    def test_statistic_schema_violations(self):
        with allure.step("Проверить три нарушения схемы статистики"):
            for bad in (c.STATISTIC_NOT_LIST, c.STATISTIC_DUP,
                        c.STATISTIC_NEGATIVE):
                http = FakeHttp(_routes(
                    {("GET", c.STATISTIC_PATH): _resp(200, bad)}))
                snapshot = _probe(http).read_snapshot(
                    c.ENDPOINT, c.LAUNCH_ID)
                assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE

    @allure.title("Пустая статистика — допустимый полный снимок")
    def test_empty_statistic_is_complete(self):
        with allure.step("Подменить statistic пустым массивом"):
            http = FakeHttp(_routes(
                {("GET", c.STATISTIC_PATH): _resp(200, c.STATISTIC_EMPTY)}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить complete и stats={}"):
            assert snapshot["outcome"] == rest.OUTCOME_COMPLETE
            assert snapshot["stats"] == {}

    @allure.title("Progress без ready или с не-bool — inconclusive")
    def test_progress_schema_violations(self):
        with allure.step("Проверить отсутствие и строковый тип ready"):
            for bad in (c.PROGRESS_NO_READY, c.PROGRESS_STRING_READY):
                http = FakeHttp(_routes(
                    {("GET", c.PROGRESS_PATH): _resp(200, bad)}))
                snapshot = _probe(http).read_snapshot(
                    c.ENDPOINT, c.LAUNCH_ID)
                assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE
                assert snapshot["ready"] is None


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("REST probe: строгий обход страниц")
@allure.severity(allure.severity_level.NORMAL)
class TestResultsPagination:

    @allure.title("Две страницы до last — полный allowlist-набор")
    def test_two_pages_complete(self):
        with allure.step("Выполнить снимок с двумя страницами"):
            http = FakeHttp(_routes())
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить complete, pagination и порядок запросов"):
            assert snapshot["outcome"] == rest.OUTCOME_COMPLETE
            assert snapshot["pagination"] == {
                "complete": True, "pages": 2, "total_elements": 3}
            assert [r["id"] for r in snapshot["results"]] == [101, 102, 103]
            page_calls = [path for method, path in _paths(http)
                          if path.startswith("/api/testresult")]
            assert page_calls == [c.results_path(0), c.results_path(1)]

    @allure.title("Пустой набор (totalElements=0, last) — complete без результатов")
    def test_empty_result_set_is_complete(self):
        with allure.step("Подменить единственную пустую last-страницу"):
            http = FakeHttp(_routes(
                {("GET", c.results_path(0)): _resp(200, c.PAGE0_EMPTY_DONE)}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить complete и пустой results"):
            assert snapshot["outcome"] == rest.OUTCOME_COMPLETE
            assert snapshot["results"] == []
            assert snapshot["pagination"] == {
                "complete": True, "pages": 1, "total_elements": 0}

    @allure.title("Ранняя пустая страница не считается концом обхода")
    def test_early_empty_page_is_inconclusive(self):
        with allure.step("Подменить первую страницу пустой без last"):
            http = FakeHttp(_routes(
                {("GET", c.results_path(0)): _resp(200, c.PAGE0_EMPTY_EARLY)}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить inconclusive и незавершённый обход"):
            assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE
            assert snapshot["pagination"]["complete"] is False
            assert ("GET", c.results_path(1)) not in _paths(http)

    @allure.title("Сервер отвечает другим number — повтор/пропуск блокируется")
    def test_page_echo_mismatch_is_inconclusive(self):
        with allure.step("Подменить вторую страницу ответом с number=0"):
            http = FakeHttp(_routes(
                {("GET", c.results_path(1)): _resp(200, c.PAGE1_ECHO_0)}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить inconclusive"):
            assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE
            assert snapshot["pagination"]["complete"] is False

    @allure.title("Повтор id результата между страницами — inconclusive")
    def test_duplicate_result_id_is_inconclusive(self):
        with allure.step("Подменить вторую страницу повтором id=101"):
            http = FakeHttp(_routes(
                {("GET", c.results_path(1)): _resp(200, c.PAGE1_DUP_ID)}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить inconclusive"):
            assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE

    @allure.title("Изменение totals между страницами — inconclusive")
    def test_totals_drift_is_inconclusive(self):
        with allure.step("Подменить вторую страницу с totalElements=4"):
            http = FakeHttp(_routes(
                {("GET", c.results_path(1)): _resp(200, c.PAGE1_SHIFTED)}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить inconclusive"):
            assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE
            assert snapshot["pagination"]["complete"] is False

    @allure.title("last до последней по totalPages страницы — inconclusive")
    def test_last_before_total_pages_is_inconclusive(self):
        with allure.step("Подменить первую страницу last=true при totalPages=2"):
            http = FakeHttp(_routes(
                {("GET", c.results_path(0)): _resp(200, c.PAGE0_LAST_EARLY)}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить inconclusive"):
            assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE

    @allure.title("last=false при исчерпанном totalPages — inconclusive")
    def test_not_last_at_end_is_inconclusive(self):
        with allure.step("Подменить страницу без last при totalPages=1"):
            http = FakeHttp(_routes(
                {("GET", c.results_path(0)): _resp(200, c.PAGE0_NOT_LAST_END)}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить inconclusive"):
            assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE

    @allure.title("Обход без last упирается в лимит страниц")
    def test_max_pages_bound_is_inconclusive(self):
        with allure.step("Подменить страницы, всегда обещающие продолжение"):
            routes = _routes()
            for index, payload in enumerate(c.PAGES_NO_END):
                routes[("GET", c.results_path(index))] = _resp(200, payload)
            http = FakeHttp(routes)
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить inconclusive на лимите max_pages"):
            assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE
            assert snapshot["pagination"]["pages"] == c.MAX_PAGES
            assert snapshot["pagination"]["complete"] is False

    @allure.title("Неполная схема результата — inconclusive, часть данных сохранена")
    def test_result_missing_field_is_inconclusive(self):
        with allure.step("Подменить страницу: валидный элемент, затем без hidden"):
            http = FakeHttp(_routes(
                {("GET", c.results_path(0)): _resp(200, c.PAGE0_BAD_FIELD)}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить inconclusive и сохранённый первый элемент"):
            assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE
            assert snapshot["pagination"]["complete"] is False
            assert [r["id"] for r in snapshot["results"]] == [101]


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("REST probe: нормализация allowlist")
@allure.severity(allure.severity_level.NORMAL)
class TestResultNormalization:

    @allure.title("hidden, retriedBy и in_progress сохраняются, лишнее отбрасывается")
    def test_allowlist_fields_preserved(self):
        with allure.step("Выполнить снимок с hidden/retry/in_progress"):
            http = FakeHttp(_routes())
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить ключи и сохранённые поля"):
            third = snapshot["results"][2]
            assert set(third) == {
                "id", "name", "status", "test_case_id", "launch_id",
                "project_id", "hidden", "retried_by_id"}
            assert third["status"] == "in_progress"
            assert third["hidden"] is True
            assert third["retried_by_id"] == 55
            assert third["test_case_id"] is None
            assert "fullName" not in third and "trace" not in third

    @allure.title("Результат с чужим launchId — inconclusive")
    def test_foreign_launch_id_is_inconclusive(self):
        with allure.step("Подменить страницу результатом другого launch"):
            http = FakeHttp(_routes(
                {("GET", c.results_path(0)): _resp(200, c.PAGE0_FOREIGN)}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить inconclusive"):
            assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("REST probe: drift launch-метаданных")
@allure.severity(allure.severity_level.NORMAL)
class TestLaunchDrift:

    @allure.title("Повторный GET: изменение closed — inconclusive")
    def test_closed_drift_is_inconclusive(self):
        with allure.step("Подменить повторный launch get изменённым closed"):
            http = FakeHttp(_routes(
                {("GET", c.LAUNCH_PATH): [
                    _resp(200, c.LAUNCH_OPEN), _resp(200, c.LAUNCH)]}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить inconclusive и два launch get"):
            assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE
            assert _paths(http).count(("GET", c.LAUNCH_PATH)) == 2

    @allure.title("Повторный GET: исчезновение launch — missing")
    def test_vanished_launch_is_missing(self):
        with allure.step("Подменить повторный launch get ответом 404"):
            http = FakeHttp(_routes(
                {("GET", c.LAUNCH_PATH): [
                    _resp(200, c.LAUNCH), _resp(404, {"status": 404})]}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить missing"):
            assert snapshot["outcome"] == rest.OUTCOME_MISSING

    @allure.title("Неизменный повторный GET сохраняет complete")
    def test_stable_recheck_keeps_complete(self):
        with allure.step("Выполнить снимок со стабильным launch"):
            http = FakeHttp(_routes())
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить complete и два launch get"):
            assert snapshot["outcome"] == rest.OUTCOME_COMPLETE
            assert _paths(http).count(("GET", c.LAUNCH_PATH)) == 2


@allure.epic("Инфраструктура")
@allure.feature("TestOps-интеграция")
@allure.story("REST probe: модель ошибок")
@allure.severity(allure.severity_level.NORMAL)
class TestOutcomeModel:

    @allure.title("403 на results после найденного launch — unreachable, не missing")
    def test_results_403_is_unreachable(self):
        with allure.step("Подменить results get ответом 403"):
            http = FakeHttp(_routes(
                {("GET", c.results_path(0)): _resp(403, "")}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить unreachable и сохранённый launch"):
            assert snapshot["outcome"] == rest.OUTCOME_UNREACHABLE
            assert snapshot["launch"]["id"] == c.LAUNCH_ID
            assert snapshot["pagination"]["complete"] is False

    @allure.title("5xx на statistic — unreachable")
    def test_statistic_5xx_is_unreachable(self):
        with allure.step("Подменить statistic ответом 500"):
            http = FakeHttp(_routes(
                {("GET", c.STATISTIC_PATH): _resp(500, "")}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить unreachable и stats=None"):
            assert snapshot["outcome"] == rest.OUTCOME_UNREACHABLE
            assert snapshot["stats"] is None

    @allure.title("Сетевая ошибка/timeout транспорта — unreachable без утечек")
    def test_transport_error_is_unreachable(self):
        with allure.step("Подменить progress исключением транспорта"):
            http = FakeHttp(_routes(
                {("GET", c.PROGRESS_PATH):
                 PreparationError("HTTP-транспорт недоступен")}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить unreachable и отсутствие деталей"):
            assert snapshot["outcome"] == rest.OUTCOME_UNREACHABLE
            assert snapshot["reason"] == "progress: transport error"
            assert c.JWT not in json.dumps(snapshot)

    @allure.title("Невалидный JSON страницы — inconclusive")
    def test_results_invalid_json_is_inconclusive(self):
        with allure.step("Подменить results битым телом"):
            http = FakeHttp(_routes(
                {("GET", c.results_path(0)): _resp(200, "not json")}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить inconclusive"):
            assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE

    @allure.title("Страница-необъект — inconclusive")
    def test_results_non_object_is_inconclusive(self):
        with allure.step("Подменить results массивом вместо Page"):
            http = FakeHttp(_routes(
                {("GET", c.results_path(0)): _resp(200, [1, 2])}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить inconclusive"):
            assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE

    @allure.title("Малформированный транспортный ответ — inconclusive")
    def test_malformed_transport_response_is_inconclusive(self):
        with allure.step("Подменить launch get объектом без status"):
            http = FakeHttp(_routes(
                {("GET", c.LAUNCH_PATH): object()}))
            snapshot = _probe(http).read_snapshot(c.ENDPOINT, c.LAUNCH_ID)
        with allure.step("Проверить inconclusive"):
            assert snapshot["outcome"] == rest.OUTCOME_INCONCLUSIVE
