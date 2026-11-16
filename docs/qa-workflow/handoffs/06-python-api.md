# Передача результата 06: Python API CAT-UPD-VAL

Дата: 2026-11-14. Статус: `ready` для интеграции кода и передачи 07;
готовность живого окружения и шесть выполненных API-сценариев не заявляются.

## Входы и решения

Прочитаны AGENTS.md, requirement v1 / scenarios v2, assessment,
00-scenario-review, 03-runtime-plan, knowledge компонентов и запуска,
локальный skill `.agents/skills/run-tests/SKILL.md`.
Приложение: base `36674280b6878540a9e88f40aaeedf5dfdd2e6ce`;
контракт авторизации/данных проверен статически в 03. Общие исходники
приложения в 06 не изменялись; параллельный fix принадлежит 05.
Координатор принял контракт для disposable compose-проекта `catupdval`:
выделенный пользователь, autoprov только по явному env-флагу, SQL строго
по ID собственной категории. Реальное окружение в этой задаче запрещено.

## Изменённые файлы и публичные компоненты

- `infrastructure/http/__init__.py`.
- `infrastructure/http/client.py`: `HttpClient(base_url, opener=None, timeout=15)`,
  `HttpResponse(status, body, headers).json()`, `PreparationError`,
  `require_status(response, expected, step)`,
  `CategoriesApi(client, token).all()/add(category)/update(category)`.
  Пример: `CategoriesApi(HttpClient(url), token).all()`.
  Один вызов метода API — один HTTP-запрос; редиректы не автоматические;
  отрицательные HTTP-ответы возвращаются как данные, без JSON-разбора,
  повторов, `raise_for_status` и автоматического логирования.
- `infrastructure/http/oauth.py`: `obtain_token(client, username, password)`,
  `register(client, username, password)`, внутренний HTML parser `Forms`,
  `local_path(client, location)`, `csrf(client, fields)`.
  Пример: `token = obtain_token(HttpClient(auth_url), username, password)`.
  PKCE S256 + state; cookie-сеанс, динамические login/consent формы;
  код из callback Location, frontend не запрашивается. Неожиданный origin,
  повторная форма после отправки, неверный state и missing token — ошибка
  подготовки. Submit/cancel и unchecked input не копируются в consent.
- `test_data/consts/category_update.py`: `INVALID_NAMES/VALID_NAMES`,
  `INVALID_IDS/VALID_IDS`, `SNAPSHOT_FIELDS`, OAuth-константы,
  префикс/лимит категорий и фиктивные данные offline-проверок.
- `tests/api/conftest.py`: `ApiSettings`, `load_api_settings(env=None)`,
  fixtures `api_settings`, `api_token`, `categories_api`, `category_db`
  (session) и `own_category` (function).
  Helpers `read_categories(api)`, `category_snapshot(api, category_id)`.
  Пример: аргументы `own_category, categories_api` в параметризованном тесте.
  Отсутствующий env/token/cleanup — error, без skip. SQL-подключение и
  проверка таблицы до создания данных; lazy import psycopg.
  Для каждого параметра: проверка коллизий/лимита → POST → сохранение UUID →
  регистрация finalizer → GET snapshot и проверка владельца/имени/archived.
  Finalizer удаляет параметризованным SQL по UUID **и username**; контрольный
  GET обязателен. Ошибка teardown остаётся ошибкой с отдельным evidence.
- `tests/api/test_category_update.py`: два параметризованных теста,
  шесть ID CAT-UPD-VAL-001…006. Негативные сначала сохраняют ответ PATCH,
  затем безусловный GET и оба snapshot, только после этого assertions 400/
  неизменности. Позитивные проверяют 200 до JSON, затем GET-состояние;
  тело PATCH проверяется отдельно как вторичный контракт.
- `tests/api/__init__.py`.
- `tests/unit/test_http_client.py`: 12 offline-случаев (с параметризацией),
  включая 400/non-JSON без второго запроса, успешный JSON, origin,
  login/consent/callback/token, чужой origin, callback state, missing env,
  finalizer до падения snapshot GET, явный orphan-risk при malformed POST.

Общие `requirements.txt`, harness, документацию и каталог интегрировал
координатор по согласованию: явные `psycopg==3.2.13` и
`psycopg-binary==3.2.13`; группа api требует SUT scope.
HTTP использует stdlib, транзитивных HTTP-пакетов нет.

## Проверки и evidence

Python 3.13.15, pytest 9.1.1, allure-pytest 2.16.2,
psycopg/psycopg-binary 3.2.13.

- `sh tools/compile-tests.sh`: exit 0, 73 collected (58 unit + 6 API + 9 UI).
  Это collection без исполнения API/UI.
- `sh tools/run-tests.sh group unit`: exit 0, **58 passed**, 0 failed,
  0 errors, 0 skipped. Последний evidence:
  `artifacts/harness/run-tr1ho9aw/` (`manifest.json`, `junit.xml`,
  `allure-results/`). Хеши новых исходников:
  `artifacts/harness/run-tr1ho9aw/api-source-identity.json`.
- Предыдущий проход до последнего уточнения SQL owner guard:
  `artifacts/harness/run-4_m5q3ha/`, 58 passed.
- `git diff --check`: exit 0.

Ни одного реального HTTP/SQL-запроса, Gradle/Docker-прогона и изменения
TestOps в задаче 06 не было. Моки подтверждают контроль потока, а не
работоспособность OAuth/cleanup на живой версии.

## Конфигурация для 07

Обязательны `API_BASE_URL`, `API_AUTH_URL`, `API_USERNAME`, `API_PASSWORD`,
`API_SPEND_DB_DSN`; значения/секреты в код не включаются.
`API_USER_AUTOPROVISION` — `true/false` (по умолчанию false).
Пользователь должен быть отдельным на прогон. При false он заранее создан;
при true регистрируется единожды за session. Пользователь сохраняется до
уничтожения disposable БД; `API_AUTH_DB_DSN` не используется, автоматического
SQL удаления пользователя нет. Финальный lifecycle окружения — задача 07.

После готовности scope/стенда команда:
`sh tools/run-tests.sh --allow-sut group api`.
Передать username/password/DSN только через защищённое окружение; не передавать
секреты pytest-параметрами, CLI URL или в evidence. Ответы OAuth, cookies,
PKCE-verifier и Authorization не прикладываются.

## Ограничения и следующий исполнитель

07 должен подтвердить readiness сервисов, идентичность сборки base/fix,
реальные login/consent/PKCE и регистрацию; у статически описанного контракта
могут отличаться rendered формы/редиректы. Ошибка формы — error, а не fallback
на учебный OAuth-клиент или фальшивый token.

Если POST прошёл, но ID невозможно извлечь (malformed JSON/missing/invalid
UUID), безопасно выбрать строку для точечного удаления нельзя. Fixture
фиксирует `category preparation orphan risk` и падает; очистку по имени
или произвольное удаление не выполняет. 07 должен проверить disposable БД
и завершить только ресурсы пилота; такой прогон не считать успешным cleanup.
При известном UUID finalizer установлен до последующих проверок и действует
при setup/assertion failure.

Не подтверждены R3/R4 на БД, реальный API baseline/head, TestOps ID/синхронизация
и доступность внешних образов. Следующий исполнитель — 07 после 03/05/06;
запуск стенда и внешние записи требуют соответствующего поручения координатора.
