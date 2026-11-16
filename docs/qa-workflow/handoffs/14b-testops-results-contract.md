# Передача результата: read-only контракт проверки результатов TestOps

Агент: `14B`. Дата: 2026-11-14. Статус: `ready` — контракт исследован,
минимальный доступ проверен живым запросом; реализация probe — отдельное
поручение (см. конец). Параллельно работал агент 14A (доступ и поиск
кейсов); его область и файлы не затрагивались.

Область записи соблюдена: этот handoff и
`artifacts/testops-readonly/14b-155530/`. Сущностей в TestOps не
создавалось, внешних записей не было, код и существующие state не
менялись. Токен загружался из корневого `.env` через `load_dotenv`
(exported env приоритетнее), передавался только внутри процесса
(форма oauth-token / `Authorization: Bearer`), нигде не печатался
и не сохранялся.

## Минимальная проверка доступа (live)

| Запрос | HTTP | Наблюдение | Evidence |
| --- | --- | --- | --- |
| `POST /api/uaa/oauth/token` (form `grant_type=apitoken`, `scope=openid`, `token=<env>`) | 200 | JWT получен: `access_token`, `expires_in`, `jti`, `scope`, `token_type` | `00-auth.txt` |
| `GET /api/launch?projectId=5444&page=0&size=3` | 200 | `PageLaunchDto`: `totalElements=0`, `totalPages=0`, `first/last/empty=true`, `content=[]` — **в проекте 5444 нет launches** | `01-launch-list.json` |
| `GET /api/launch/0` | 404 | тело `{status:404, message:"Not Found", timestamp}` | `07-launch-notfound.json` |
| `GET /api/testresult?launchId=0&page=0&size=1` | 403 | `Forbidden` — для несуществующего launch отдаётся 403, а не пустая страница | `08-testresult-empty.json` |
| `GET /api/launch/0/progress` | 403 | `Forbidden` | `09-progress-notfound.json` |
| `allurectl -o json launch list --project-id 5444 -q true` | exit 0 | stdout `[]` — **голый массив, без page-обёртки** | stdout (не сохранён, пусто) |
| `allurectl -o json test-case list --project-id 5444 -q 'name ~= "ZZZ-NOSUCH-14B"'` | exit 0 | stdout `[]` — голый массив | stdout (не сохранён, пусто) |

Токен валиден (oauth exchange 200), чтение `/api/launch` разрешено.
Проект пуст: живую форму `LaunchDto` со статистикой, `progress` и
`TestResultDto` проверить негде — ниже они подтверждены **только
OpenAPI** и не должны считаться фактическим ответом сервера.

## Источники

- OpenAPI инстанса: `GET https://allure.qa.guru/api-docs` (без авторизации),
  `openapi 3.1.0`, `allure-testops-service` версия `527u01`, 622 пути.
  Swagger UI на `/swagger-ui/index.html` (JS-страница; JSON — только
  `/api-docs`). Дистиллят: `02-openapi-extract.json`.
- `docs.qameta.io/reference/api/` — Bearer-auth через
  `POST /api/uaa/oauth/token`; upload только поддерживаемыми инструментами.
- `docs.qameta.io/.../launches-overview/` — обработка launch происходит
  **после его закрытия** («Only after a launch has been closed, Allure
  TestOps will process it»); реран создаёт новый job run и **не заменяет**
  ранее загруженную историю launch.
- Локально: `allurectl 2.24.0 launch get/list --help` — колонки
  `ID, Name, Tags, Passed, Failed, Broken, Skipped, Ready`.

## Подтверждённые endpoint'ы и поля (OpenAPI 527u01)

Все запросы GET, auth = `Authorization: Bearer <jwt>`.

| Задача probe | Method/path | Параметры | Ответ 200 |
| --- | --- | --- | --- |
| launch + project | `GET /api/launch/{id}` | `id` path | `LaunchDto`: `id`, `name`, `projectId`, `closed`, `autoclose`, `external`, `createdDate`, `tags`, `issues`, `links`, `createdBy`, `lastModifiedDate`. **Статистики и ready нет** |
| список launches | `GET /api/launch` | `projectId` (обяз.), `page=0`, `size=10`, `sort=[created_date,DESC]` | `PageLaunchDto` (content=LaunchDto) |
| поиск launches AQL | `GET /api/launch/__search` | `projectId`, `rql` (обяз.), page/size/sort | `PageLaunchDto` |
| статистика | `GET /api/launch/{id}/statistic` | `id` | **массив** `{status: TestStatus, count: int}` |
| признак обработки | `GET /api/launch/{id}/progress` | `id` | `{ready: boolean}` |
| результаты launch | `GET /api/testresult` | `launchId` (обяз.), `page=0`, `size=10`, `sort=[createdDate,DESC]` | `PageTestResultDto` → `TestResultDto` |
| результаты AQL | `GET /api/testresult/__search` | `projectId`, `rql`, page/size/sort | `PageTestResultRowDto` → `TestResultRowDto`: `id`, `name`, `status`, `testCaseId`, `duration`, `flaky`, `flakyCandidate`, `assignee` |
| retries launch | `GET /api/launch/{id}/retries` | page/size/`sort=[status,ASC]` | `PageTestResultRetriesRowDto` → `id`, `name`, `status`, `testCaseId`, `totalRetries`, `previousRetry{id,name,status}` |
| история результата | `GET /api/testresult/{id}/retries` | page/size/`sort=[start,DESC]` | `PageTestResultHistoryDto` |
| плоский список (v2) | `GET /api/v2/launch/{launchId}/test-result/flat` | `search`, `filterId`, `page=0`, `size=100`, `sort=[name,ASC]` | `PageTestResultFlatDto` → `id`, `name`, `status`, `testCaseId`, `hidden`, `manual`, `flaky`, `layerName` |

`TestResultDto` (поля, нужные probe): `id`, `name`, `status`,
`testCaseId`, `launchId`, `projectId`, `hidden`, `muted`, `flaky`,
`retriedBy{id,name}`, `fullName`, `historyKey`, `external`,
`start`, `stop`, `createdDate`. Полные сообщения/trace/parameters
в листинге присутствуют, но probe их читать не должен.

`TestStatus` enum: `failed`, `broken`, `passed`, `skipped`,
`unknown`, `in_progress` — все в нижнем регистре.

## Пагинация

Spring Data `Page`: `content`, `totalElements`, `totalPages`,
`number` (0-based), `size`, `numberOfElements`, `first`, `last`,
`empty`, `pageable`, `sort`. Подтверждено live на пустой странице
(01-launch-list). Условие завершения обхода: `last==true` (или
`number+1 >= totalPages`, или `content` пуст). Для детерминированного
обхода при возможной конкурентной записи рекомендуется явный
`sort=id,ASC` вместо дефолтного `createdDate,DESC`.

## Признак обработки

- `GET /api/launch/{id}/progress` → `{ready}` — единственный
  документированный индикатор завершения обработки; колонка `Ready`
  в `allurectl launch get --format`, вероятно, выводится из него
  (live не подтверждено — нет launches).
- `LaunchDto.closed` — закрытие launch; по документации обработка
  (статистика, авто-кейсы) идёт после close. `closed=false` или
  `ready=false` при нулевой статистике = обработка не завершена
  → `inconclusive`, а не `empty`/retry-safe. Это снимает
  ограничение из handoff 13 («нулевая статистика может означать
  задержку»): вердикт `empty` допустим только при `ready=true`.

## Retries и несколько результатов на кейс

- Документация: реран создаёт новый job run в том же launch и не
  заменяет историю; повторная загрузка батча создаёт дополнительные
  строки результатов, а не перезапись.
- API: у `TestResultDto` есть `retriedBy{id,name}` и `hidden`;
  сводка цепочек — `/api/launch/{id}/retries` (`totalRetries`,
  `previousRetry`). Точная семантика `hidden` (скрытие superseded-
  результатов из статистики) в OpenAPI не описана — только поле.
- Для probe: несколько строк на один сценарий/кейс = аномалия,
  фиксируется как mismatch/anomaly. **«Последний» результат молча
  не выбирается.** Если `hidden` позже подтвердится как «заменён
  retry», не-hidden строка может считаться актуальной, но само
  наличие retry-цепочки — отдельный флаг в отчёте.

## Что проверено live / только по документации

- Live: auth-обмен, page-обёртка, 404 launch, 403 на
  results/progress для несуществующего launch, пустой проект,
  голые массивы в `allurectl -o json`.
- Только OpenAPI: поля `LaunchDto`/`TestResultDto`,
  `/statistic`, `/progress`, `/retries`, v2 flat, порядок
  статусов, семантика `ready`/`hidden`/`closed`, поведение при
  непустых страницах.
- Не проверено и не подтверждено: содержит ли `/api/testresult`
  hidden-результаты в выдаче; поведение при `launchId` чужого
  проекта; rate-limits; JSON-форма `allurectl launch get -o json`.

## Несовместимости текущих парсеров

1. `client.parse_launch` ищет stats внутри JSON launch
   (`statistic`/`stats`/плоские ключи). REST `GET /api/launch/{id}`
   их не содержит — для REST-транспорта stats берутся отдельным
   вызовом `/statistic`, чей формат (`[{status,count}]`) **другой**:
   `_stat_counts` его не разберёт. Нужен отдельный парсер
   `TestStatusCount[] -> {status: count}`.
2. `parse_launch` на `LaunchDto` REST вернёт `stats=None` →
   `inconclusive` — не ошибка, но stats-проверка через REST так
   не получить. Для `allurectl launch get -o json` фактическая
   форма неизвестна (нет launch для пробы).
3. `parse_launch_results` совместим по полям (`name`, `status`,
   `testCaseId`; `_json_payload` разворачивает `content`), но:
   - ожидает список одной порции; многостраничный обход — задача
     транспорта (склеить `content` всех страниц до вызова парсера
     или возвращать готовый list[dict]);
   - не читает `hidden`/`retriedBy`/`id` — для детекции дублей и
     superseded-строк probe должен передавать их отдельно или
     фильтровать до парсера;
   - статусы `in_progress`/`unknown` пройдут `str.lower()` и
     попадут в сравнение как mismatch — приемлемо, но лучше явно
     трактовать `in_progress` как «обработка не завершена».
4. `allurectl` как транспорт probe не подходит: `launch list`
   отдаёт голый массив без page-метаданных и без `--page`; per-result
   чтения нет (подтверждено повторно на 2.24.0).
5. 403 на `/api/testresult` при несуществующем launch: probe обязан
   сначала делать `GET /api/launch/{id}` (404 → `missing`), иначе
   403 неотличим от «нет прав». 403 на любом шаге после успешного
   launch-get → `unreachable`/`inconclusive`, не `missing`.

## Ограничения автоматического подтверждения

- Семантика `ready` и `hidden` подтверждена только схемой — первый
  живой прогон должен сверить `progress`/`closed` со статистикой
  вручную, прежде чем `ready` станет гейтом для `empty`.
- `/statistic` считается сервером после close; на открытом launch
  набор может быть неполным без ошибки — `partial`/`inconclusive`,
  не `failed`.
- Проект 5444 пуст: кейсов и launches нет; привязки
  `testops_id` проверить не на чем (область 14A).

## Поручение разработчику: per-result REST probe

1. Новый транспорт (напр. `infrastructure/reporting/testops/rest.py`),
   **без** изменения `allurectl`-пути upload:
   - `_jwt(endpoint)` → `POST /api/uaa/oauth/token`
     (`grant_type=apitoken`, `scope=openid`, `token=<ALLURE_TOKEN>`
     в теле формы; токен из env, заголовок собирается внутри
     процесса, таймаут ~20–30 с, без verbose). Один обмен на probe.
   - `get_launch(endpoint, launch_id)` → `GET /api/launch/{id}`:
     200 → `{id,name,project_id,closed}`; 404 → `missing`;
     прочее → `unreachable`.
   - `get_progress(endpoint, launch_id)` → `{ready}` или None.
   - `get_statistic(endpoint, launch_id)` → `{status:count}` через
     новый парсер `TestStatusCount[]` (в `client.py` или rest.py).
   - `list_launch_results(endpoint, launch_id)` → обход
     `GET /api/testresult?launchId=N&sort=id,ASC&size=100&page=i`
     до `last==true`; на выходе `list[dict]` минимум с
     `id,name,status,test_case_id,hidden,retriedBy_id`. Сохранять
     allowlist-поля, тела/attachments не тянуть.
   - Возвраты — структурированные значения или `CommandResult`,
     совместимые с `lifecycle._launch_results_check`.
2. Подключение к `perform_verify`: REST-транспорт реализует тот же
   duck-typing (`get_launch`, `list_launches` не обязателен —
   `projectId` есть в `LaunchDto`, fallback `__search` возможен).
3. Уточнение вердиктов (изменение lifecycle — отдельное решение
   координатора): при `result_set == "empty"` и `ready == false`
   или `closed == false` → `inconclusive` вместо `empty`; `empty`
   остаётся только при `ready == true`. Статус `in_progress` в
   наблюдаемых результатах трактовать как «обработка не завершена».
4. Сравнение результатов: ровно одна строка на сценарий;
   `hidden=true` и retry-цепочки (`retriedBy`/`totalRetries>0`) —
   аномалия в отчёт, а не молчаливый выбор «последнего». Лишние
   строки (не подходящие ни под один `SID:`) — foreign/mismatch.
5. Offline-тесты (фейковый transport/HTTP-слой):
   - сбор двух+ страниц до `last`; обрыв при `content=[]`;
   - 404 launch → `missing`; 403/5xx → `unreachable`/`inconclusive`;
   - `ready=false` + нулевая статистика → не `empty`;
   - `ready=true` + нулевая → `empty`;
   - дубли строк на сценарий и `hidden` → mismatch/anomaly;
   - `in_progress`-статус → не подтверждён;
   - битый JSON/нечитаемая схема → inconclusive, без угадывания;
   - статистика `[{status,count}]` → корректная сводка;
   - JWT не попадает в логи/исключения/сохранённые поля.

## Команды и проверки этого агента

| Шаг | Результат |
| --- | --- |
| `allurectl --version`, `launch get/list --help` | 2.24.0; колонки и флаги зафиксированы локально |
| `GET /api-docs` (без auth) | 200, OpenAPI 3.1.0, 622 пути |
| python (`.venv`): dotenv + urllib, 8 HTTPS-вызовов | statuses выше; JWT не записывался |
| `allurectl launch list`/`test-case list -o json` | exit 0, `[]` |

Evidence: `artifacts/testops-readonly/14b-155530/`
(`00-auth.txt`, `01-launch-list.json`, `02-openapi-extract.json`,
`07-launch-notfound.json`, `08-testresult-empty.json`,
`09-progress-notfound.json`).
