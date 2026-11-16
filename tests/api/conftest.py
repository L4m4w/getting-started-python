"""Fixtures только для явно настроенного изолированного API-окружения."""
import json
import os
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import allure
import pytest

from infrastructure.http.client import CategoriesApi, HttpClient, PreparationError, require_status
from infrastructure.http.oauth import obtain_token, register
from test_data.consts.category_update import CATEGORY_NAME_PREFIX, MAX_ACTIVE_CATEGORIES, SNAPSHOT_FIELDS
from test_data.users import MissingTestDataError


@dataclass(frozen=True)
class ApiSettings:
    base_url: str
    auth_url: str
    username: str
    password: str = field(repr=False)
    spend_db_dsn: str = field(repr=False)
    autoprov: bool = False


def load_api_settings(env=None):
    env = os.environ if env is None else env
    names = ("API_BASE_URL", "API_AUTH_URL", "API_USERNAME", "API_PASSWORD", "API_SPEND_DB_DSN")
    missing = [name for name in names if not env.get(name)]
    if missing:
        raise MissingTestDataError("Не заданы: " + ", ".join(missing))
    flag = env.get("API_USER_AUTOPROVISION", "false").lower()
    if flag not in ("true", "false"):
        raise MissingTestDataError("API_USER_AUTOPROVISION должен быть true/false")
    return ApiSettings(*(env[name] for name in names), autoprov=flag == "true")


def read_categories(api):
    body = require_status(api.all(), 200, "GET categories").json()
    if not isinstance(body, list) or any(not isinstance(item, dict) for item in body):
        raise PreparationError("GET categories: ожидался список объектов")
    return body


def category_snapshot(api, category_id):
    found = [item for item in read_categories(api) if item.get("id") == category_id]
    if len(found) != 1 or any(key not in found[0] for key in SNAPSHOT_FIELDS):
        raise PreparationError("GET categories: собственная категория отсутствует или snapshot неполный")
    return {key: found[0][key] for key in SNAPSHOT_FIELDS}


@pytest.fixture(scope="session")
def api_settings():
    return load_api_settings()


@pytest.fixture(scope="session")
def api_token(api_settings):
    auth = HttpClient(api_settings.auth_url)
    if api_settings.autoprov:
        register(auth, api_settings.username, api_settings.password)
    return obtain_token(auth, api_settings.username, api_settings.password)


@pytest.fixture(scope="session")
def categories_api(api_settings, api_token):
    return CategoriesApi(HttpClient(api_settings.base_url), api_token)


@pytest.fixture(scope="session")
def category_db(api_settings):
    try:
        import psycopg
        connection = psycopg.connect(api_settings.spend_db_dsn, connect_timeout=10, autocommit=True)
    except Exception:
        raise PreparationError("Не удалось подключить SQL cleanup к пилотной БД") from None
    try:
        # Проверка до создания первой категории: cleanup должен быть доступен.
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM category LIMIT 0")
        yield connection
    finally:
        connection.close()


@pytest.fixture
def own_category(request, categories_api, category_db, api_settings):
    target_name = request.getfixturevalue("name")
    categories = read_categories(categories_api)
    if sum(not item.get("archived", False) for item in categories) >= MAX_ACTIVE_CATEGORIES:
        raise PreparationError("Достигнут лимит активных категорий; чужие данные не удаляются")
    if any(item.get("name") == target_name for item in categories):
        raise PreparationError("Коллизия целевого имени; чужие данные не удаляются")
    name = CATEGORY_NAME_PREFIX + uuid4().hex
    if any(item.get("name") == name for item in categories):
        raise PreparationError("Коллизия исходного имени")
    response = categories_api.add({"name": name, "archived": False})
    try:
        result = require_status(response, 200, "POST category").json()
    except PreparationError:
        allure.attach(json.dumps({"name": name, "post_status": response.status,
                                  "cleanup": "ID unknown; creation may have succeeded; inspect disposable DB"}),
                      "category preparation orphan risk", allure.attachment_type.JSON)
        raise
    if not isinstance(result, dict) or not result.get("id"):
        allure.attach(json.dumps({"name": name, "cleanup": "ID missing; inspect disposable DB"}),
                      "category preparation orphan risk", allure.attachment_type.JSON)
        raise PreparationError("POST category: ID не получен; требуется диагностика созданных данных")
    try:
        category_id = str(UUID(result["id"]))
    except (ValueError, TypeError, AttributeError):
        allure.attach(json.dumps({"name": name, "cleanup": "invalid ID; inspect disposable DB"}),
                      "category preparation orphan risk", allure.attachment_type.JSON)
        raise PreparationError("POST category: невалидный UUID, cleanup невозможен") from None

    def cleanup():
        try:
            with category_db.cursor() as cursor:
                cursor.execute("DELETE FROM category WHERE id = %s AND username = %s",
                               (category_id, api_settings.username))
            remaining = read_categories(categories_api)
            if any(item.get("id") == category_id for item in remaining):
                raise PreparationError("Категория осталась после SQL cleanup")
        except Exception:
            allure.attach("Ошибка точечного cleanup собственной категории", "cleanup", allure.attachment_type.TEXT)
            raise PreparationError("Ошибка teardown категории; проверьте evidence cleanup") from None
        allure.attach(json.dumps({"id": category_id, "deleted": True}), "cleanup", allure.attachment_type.JSON)

    request.addfinalizer(cleanup)
    snapshot = category_snapshot(categories_api, category_id)
    if (snapshot["username"] != api_settings.username or snapshot["name"] != name
            or snapshot["archived"] is not False):
        raise PreparationError("POST/GET: неверный владелец, исходное имя или archived")
    return snapshot
