import io
import json
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlencode, urlsplit

import allure
import pytest

from infrastructure.http.client import CategoriesApi, HttpClient, HttpResponse, PreparationError, require_status
from infrastructure.http.oauth import Forms, local_path, obtain_token
from test_data.consts.category_update import (
    OAUTH_REDIRECT_URI, UNIT_BAD_ORIGINS, UNIT_CATEGORY, UNIT_CONSENT_HTML,
    UNIT_ERROR_BODY, UNIT_FOREIGN_LOCATION, UNIT_JSON, UNIT_LOGIN_HTML,
    UNIT_ORIGIN, UNIT_PASSWORD, UNIT_TOKEN,
)
from tests.api.conftest import load_api_settings, own_category
from test_data.users import MissingTestDataError


@allure.epic("Инфраструктура")
@allure.feature("HTTP транспорт")
@allure.story("Один вызов — один запрос")
@allure.severity(allure.severity_level.CRITICAL)
@allure.title("HTTP ошибка возвращается без повторного запроса и без JSON-разбора")
def test_error_response_is_not_retried():
    with allure.step("Подменить транспорт отрицательным не-JSON ответом"):
        opener = Mock()
        opener.open.side_effect = HTTPError(UNIT_ORIGIN, 400, "", {}, io.BytesIO(UNIT_ERROR_BODY))
        client = HttpClient(UNIT_ORIGIN, opener=opener)
        response = CategoriesApi(client, UNIT_TOKEN).update(UNIT_CATEGORY)
    with allure.step("Проверить единственный PATCH и доступность исходного тела"):
        assert response.status == 400 and response.body == UNIT_ERROR_BODY
        opener.open.assert_called_once()
        assert opener.open.call_args.args[0].method == "PATCH"
        with pytest.raises(PreparationError, match="ожидался HTTP"):
            require_status(response, 200, "PATCH")


@allure.epic("Инфраструктура")
@allure.feature("HTTP транспорт")
@allure.story("Успешный ответ")
@allure.severity(allure.severity_level.NORMAL)
@allure.title("JSON разбирается после проверки статуса без второго запроса")
def test_success_response_is_not_requested_twice():
    with allure.step("Вернуть успешный ответ через подмену opener"):
        wire = Mock()
        wire.code, wire.headers = 200, {}
        wire.read.return_value = UNIT_JSON
        wire.__enter__ = Mock(return_value=wire)
        wire.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = wire
        response = HttpClient(UNIT_ORIGIN, opener=opener).request("GET", "/")
    with allure.step("Проверить JSON и число HTTP запросов"):
        assert require_status(response, 200, "GET").json() == json.loads(UNIT_JSON)
        opener.open.assert_called_once()


@allure.epic("Инфраструктура")
@allure.feature("HTTP транспорт")
@allure.story("Граница origin")
@allure.severity(allure.severity_level.CRITICAL)
@allure.title("Неоднозначный origin отвергается до запроса")
@pytest.mark.parametrize("origin", UNIT_BAD_ORIGINS)
def test_invalid_origin(origin):
    with allure.step("Проверить отказ невалидному origin"):
        with pytest.raises(PreparationError):
            HttpClient(origin)


@allure.epic("Инфраструктура")
@allure.feature("OAuth PKCE")
@allure.story("Протокольные переходы")
@allure.severity(allure.severity_level.CRITICAL)
@allure.title("Login и consent обрабатываются без запроса callback frontend")
def test_pkce_login_consent_and_callback():
    with allure.step("Подготовить протокольные ответы без сети"):
        calls = []
        state = None
        def request(method, path, **kwargs):
            nonlocal state
            calls.append((method, path, kwargs))
            if len(calls) == 1:
                state = parse_qs(urlsplit(path).query)["state"][0]
                return HttpResponse(302, b"", {"Location": "/login"})
            if len(calls) == 2:
                return HttpResponse(200, UNIT_LOGIN_HTML, {})
            if len(calls) == 3:
                return HttpResponse(200, UNIT_CONSENT_HTML, {})
            if len(calls) == 4:
                return HttpResponse(302, b"", {"Location": OAUTH_REDIRECT_URI + "?" + urlencode(dict(code="code", state=state))})
            return HttpResponse(200, json.dumps(dict(access_token=UNIT_TOKEN)).encode(), {})
        client = SimpleNamespace(base_url=UNIT_ORIGIN, cookies=[], request=request)
        token = obtain_token(client, UNIT_CATEGORY["username"], UNIT_PASSWORD)
    with allure.step("Проверить code exchange и отсутствие лишних полей consent"):
        assert token == UNIT_TOKEN and len(calls) == 5
        assert calls[-1][1] == "/oauth2/token"
        assert calls[-1][2]["form"]["code_verifier"]
        assert "cancel" not in calls[3][2]["form"]
        assert calls[3][2]["form"]["scope"] == "openid"
        assert all(not path.startswith("http") for _, path, _ in calls)


@allure.epic("Инфраструктура")
@allure.feature("OAuth PKCE")
@allure.story("Граница origin")
@allure.severity(allure.severity_level.CRITICAL)
@allure.title("Редирект на чужой origin не получает credentials")
def test_oauth_rejects_foreign_origin():
    with allure.step("Проверить отказ внешнему переходу"):
        with pytest.raises(PreparationError, match="origin"):
            local_path(SimpleNamespace(base_url=UNIT_ORIGIN), UNIT_FOREIGN_LOCATION)


@allure.epic("Инфраструктура")
@allure.feature("API fixtures")
@allure.story("Явная конфигурация")
@allure.severity(allure.severity_level.CRITICAL)
@allure.title("Отсутствующие настройки дают ошибку подготовки")
def test_missing_api_settings():
    with allure.step("Проверить отказ при отсутствии переменных окружения"):
        with pytest.raises(MissingTestDataError, match="API_SPEND_DB_DSN"):
            load_api_settings({})


@allure.epic("Инфраструктура")
@allure.feature("API fixtures")
@allure.story("Очистка своей категории")
@allure.severity(allure.severity_level.CRITICAL)
@allure.title("Teardown регистрируется до повторного GET и удаляет строго свой ID")
def test_cleanup_registered_even_if_snapshot_read_fails():
    with allure.step("Подменить API и SQL без сетевых операций"):
        api = Mock()
        api.all.side_effect = [HttpResponse(200, b"[]", {}), HttpResponse(500, UNIT_ERROR_BODY, {}), HttpResponse(200, b"[]", {})]
        api.add.return_value = HttpResponse(200, json.dumps(UNIT_CATEGORY).encode(), {})
        cursor = Mock()
        db = Mock()
        db.cursor.return_value.__enter__ = Mock(return_value=cursor)
        db.cursor.return_value.__exit__ = Mock(return_value=False)
        finalizers = []
        request = SimpleNamespace(getfixturevalue=lambda _: "AA", addfinalizer=finalizers.append)
    with allure.step("Получить ошибку snapshot после POST и выполнить зарегистрированный teardown"):
        with pytest.raises(PreparationError, match="GET categories"):
            own_category.__wrapped__(request, api, db, SimpleNamespace(username=UNIT_CATEGORY["username"]))
        assert len(finalizers) == 1
        finalizers[0]()
    with allure.step("Проверить параметризованный DELETE и контрольный GET"):
        cursor.execute.assert_called_once_with("DELETE FROM category WHERE id = %s AND username = %s",
                                               (UNIT_CATEGORY["id"], UNIT_CATEGORY["username"]))
        assert api.all.call_count == 3


@allure.epic("Инфраструктура")
@allure.feature("API fixtures")
@allure.story("Ошибка ответа создания")
@allure.severity(allure.severity_level.CRITICAL)
@allure.title("Некорректный ответ POST фиксирует риск данных без известного ID")
def test_malformed_creation_reports_orphan_risk(monkeypatch):
    with allure.step("Подменить успешный POST некорректным JSON"):
        api = Mock()
        api.all.return_value = HttpResponse(200, b"[]", {})
        api.add.return_value = HttpResponse(200, UNIT_ERROR_BODY, {})
        request = SimpleNamespace(getfixturevalue=lambda _: "AA", addfinalizer=Mock())
        attach = Mock()
        monkeypatch.setattr(allure, "attach", attach)
    with allure.step("Проверить ошибку и явную диагностику cleanup вместо ложного успеха"):
        with pytest.raises(PreparationError, match="JSON"):
            own_category.__wrapped__(request, api, Mock(), SimpleNamespace(username=UNIT_CATEGORY["username"]))
        request.addfinalizer.assert_not_called()
        assert "ID unknown" in attach.call_args.args[0]


@allure.epic("Инфраструктура")
@allure.feature("OAuth PKCE")
@allure.story("Проверка callback state")
@allure.severity(allure.severity_level.CRITICAL)
@allure.title("Callback с неверным state не обменивается на token")
def test_oauth_rejects_callback_without_state():
    with allure.step("Вернуть callback без state"):
        client = SimpleNamespace(base_url=UNIT_ORIGIN, cookies=[], request=Mock())
        client.request.return_value = HttpResponse(302, b"", {"Location": OAUTH_REDIRECT_URI + "?code=code"})
    with allure.step("Проверить отказ до token exchange"):
        with pytest.raises(PreparationError, match="state"):
            obtain_token(client, UNIT_CATEGORY["username"], UNIT_PASSWORD)
        client.request.assert_called_once()
