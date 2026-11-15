# Фикстуры

[Оглавление каталога](README.md)

Фикстуры `settings` и `driver` объявлены в `conftest.py`, фикстуры
тестовых данных подключены через `pytest_plugins` в `conftest.py`.

| Компонент | Путь импорта | Назначение | Пример использования |
| --- | --- | --- | --- |
| `settings` | `conftest.settings` | Session-фикстура `Settings`: собирается из CLI-опций `--browser`/`--bversion` и env через `load_settings` | Аргумент `settings` в тесте; передаётся в Page Object: `LoginPage(driver, settings)` |
| `driver` | `conftest.driver` | Function-фикстура WebDriver: создаётся через `create_driver(settings)`, закрывается `quit()` в `finally` | Аргумент `driver` в тесте; передаётся в Page Object |
| `existing_user` | pytest-плагин `test_data.fixtures` | Session-фикстура существующего пользователя из окружения; аккаунт только читается, без teardown | Аргумент `existing_user` в тесте; данные: `existing_user.username` |
| `new_user` | pytest-плагин `test_data.fixtures` | Фикстура новых уникальных учётных данных на каждый тест | Аргумент `new_user` в тесте; данные: `new_user.username` |

Ограничение очистки: на стенде niffler.qa.guru нет подтверждённого механизма
удаления пользователей, поэтому `new_user` не имеет teardown — созданные
при регистрации пользователи накапливаются на стенде.

## Изолированный API-пилот

Fixtures ниже находятся в `tests/api/conftest.py`, доступны только тестам
`tests/api/`. Входы и ограничения описаны в
[инструкции запуска](../testing/run-tests.md#api-пилот-cat-upd-val).

| Компонент | Путь | Назначение | Пример использования |
| --- | --- | --- | --- |
| `api_settings` / `load_api_settings` | `tests.api.conftest` | Обязательные API env, секретные поля исключены из repr, отсутствие env даёт ошибку подготовки | Аргумент `api_settings` в fixture |
| `api_token` | `tests.api.conftest` | Session JWT из PKCE; регистрация только по явному флагу | Аргумент `api_token` в fixture |
| `categories_api` | `tests.api.conftest` | Session `CategoriesApi` с token | `categories_api.update(snapshot)` |
| `category_db` | `tests.api.conftest` | Session psycopg connection только к явно выбранной пилотной БД, закрывается в teardown | Аргумент `category_db` в fixture |
| `own_category` | `tests.api.conftest` | Независимая категория на параметр `name`, snapshot до PATCH, finalizer удаляет только её ID и проверяет GET | Аргумент `own_category` в API-тесте |
| `read_categories`, `category_snapshot` | `tests.api.conftest` | Проверяют статус GET до JSON; чтение четырёх полей по уникальному ID | `category_snapshot(categories_api, category_id)` |

Пользователь пилота остаётся до удаления disposable окружения. Реальная
работоспособность token/cleanup подтверждена прогоном 07 на disposable-стеке;
это не подтверждает готовность произвольного нового окружения.
