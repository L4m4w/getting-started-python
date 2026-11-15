# 18B: read-only серверный preflight финальной bind-публикации

Агент: `18B`. Время свежего снимка: **2026-11-15T12:28:36–12:28:41Z**.
Статус: **ready** — серверное состояние проверено read-only вызовами,
противоречий согласованной bind-публикации не найдено. Сам preflight не
является разрешением на upload: внешние write-вызовы не выполнялись.

Разрешённая запись соблюдена: этот handoff и
`artifacts/testops-preflight/18b-20261115T122510Z/`. Общий
`artifacts/testops/` не изменялся и не блокировался; его state не открывался.
Stateful CLI `plan/status/assign/package/resolve/
verify/upload`, Docker/Gradle/API/UI, create/upload/close/watch, adoption,
recovery, commit/push/PR не вызывались.

## 1. Окружение и доступ

- Окружение загружено штатным `tools.testops.load_environment()`; его
  `load_dotenv(..., override=False)` сохраняет приоритет exported env.
- После загрузки `ALLURE_ENDPOINT` и `ALLURE_PROJECT_ID` не установлены;
  effective значения — `https://allure.qa.guru` / **5444**, как требует
  поручение. `ALLURE_TOKEN` присутствует; значение не выводилось и не
  сохранялось.
- `allurectl`: `/Users/zenalark/.local/bin/allurectl`, **2.24.0**, sha256
  `5928e200ba7e82e7c2b13c4d22d9ec1fd415e932445422b9253acfd5f62c1fba`.
- Token exchange `POST /api/uaa/oauth/token` выполнен только для read-only
  JWT; headers, JWT и сырые ответы не сохранялись. Права записи токена
  **не проверялись**: первый будущий `launch create` может вернуть 401/403.

## 2. Проект

| Проверка | Результат |
| --- | --- |
| `allurectl --endpoint https://allure.qa.guru -o json project get 5444` | exit 0 |
| id / name | `5444` / `ai_project_Larkin_EA` |

Чужие проекты не перечислялись.

## 3. Проверенные case bindings

Каждый ID прочитан `GET /api/testcase/{id}` после token exchange. Во всех
шести ответах HTTP 200, returned ID совпадает с ожидаемым, `projectId=5444`,
имя начинается точным префиксом `<SID>:`, `automated=true`, `external=true`.

| Scenario | Case ID | Префикс на сервере | Вердикт |
| --- | ---: | --- | --- |
| CAT-UPD-VAL-001 | 55376 | `CAT-UPD-VAL-001` | OK |
| CAT-UPD-VAL-002 | 55374 | `CAT-UPD-VAL-002` | OK |
| CAT-UPD-VAL-003 | 55375 | `CAT-UPD-VAL-003` | OK |
| CAT-UPD-VAL-004 | 55377 | `CAT-UPD-VAL-004` | OK |
| CAT-UPD-VAL-005 | 55373 | `CAT-UPD-VAL-005` | OK |
| CAT-UPD-VAL-006 | 55378 | `CAT-UPD-VAL-006` | OK |

Противоречий согласованному mapping не найдено.

## 4. Inventory пилотных кейсов и полнота

Основное доказательство — постраничный REST endpoint, подтверждённый в
OpenAPI 527u01, а не bare array CLI:

```text
GET /api/testcase?projectId=5444&page=0&size=100
```

| Поле | Значение |
| --- | --- |
| HTTP | 200 |
| page / items | 0 / 6 |
| totalElements / totalPages | 6 / 1 |
| last | true |
| walk complete | true |
| pilot IDs | 55373, 55374, 55375, 55376, 55377, 55378 |
| unexpected pilot IDs | 0 |
| foreign count | 0 |

Полнота доказана: обход дошёл до `last=true`, собранное число строк равно
`totalElements=6`, все шесть элементов — ожидаемые пилотные кейсы. CLI
`test-case list -q 'name ~= "CAT-UPD-VAL"'` и контроль `-q 'id >= 0'`
также вернули по шесть элементов, но использовались только как вторичный
сигнал: их голый массив сам по себе полноту не доказывает.

## 5. Поиск launch и следов execution

Целевое имя: `CAT-UPD-VAL run-ni_5bvnc final17-20261115`.

| Проверка | Результат |
| --- | --- |
| CLI exact `launch list -q 'name = "<target>"'` | exit 0, 0 matches |
| CLI `launch list -q 'name ~= "run-ni_5bvnc"'` | exit 0, 0 matches |
| CLI `launch list -q 'name ~= "CAT-UPD-VAL"'` | exit 0, только старый launch 57316 |
| REST `GET /api/launch?projectId=5444&page=0&size=100` | HTTP 200, `totalElements=1`, `totalPages=1`, `last=true` |

REST page-walk доказывает, что в проекте на момент снимка был ровно один
launch — старый 57316. Совпадающего target name и других следов
`run-ni_5bvnc` на сервере нет. Кандидатов для adoption нет; ничего не
создавалось и не переиспользовалось.

## 6. Старый launch 57316 до публикации

Безопасные поля для последующего сравнения:

| Поле | Значение |
| --- | --- |
| `GET /api/launch/57316` | HTTP 200 |
| id / projectId | 57316 / 5444 |
| name | `CAT-UPD-VAL run-5tsmzg1d pilot16-20261115` |
| closed | true |
| `GET /api/launch/57316/progress` | HTTP 200, `ready=true` |
| `GET /api/launch/57316/statistic` | HTTP 200, `{passed: 6}` |

Это read-only снимок; результатные тела, attachments и другие поля не
сохранялись.

## 7. Инструментальный контракт и план одной публикации

Help `allurectl 2.24.0` доступен (exit 0): `upload` содержит
`--project-id`, `--launch-id`, `--launch-name`; отдельная команда
`launch close <id>` присутствует. Это совпадает с контрактом 16B.

После отдельной явной авторизации фаза публикации должна остаться одной
попыткой без самостоятельных повторов:

1. Повторить локальную проверку state/package и свежий server preflight.
2. Один штатный upload:
   ```sh
   sh tools/run-testops.sh upload --execution run-ni_5bvnc --execute \
     --launch-name 'CAT-UPD-VAL run-ni_5bvnc final17-20261115'
   ```
   Exit 0 означает `sent`, а не `uploaded`.
3. Read-only проверить recorded launch: ID, projectId=5444, имя и `closed`.
4. Если `closed=false`, один согласованный close:
   ```sh
   allurectl --endpoint https://allure.qa.guru -o json launch close <recorded-launch-id>
   ```
   Факт close перечитывать `GET /api/launch/{id}`; автоматический повтор
   запрещён.
5. Ждать обработки read-only до 10 минут с интервалом 15 секунд:
   `GET /api/launch/{id}/progress` (`ready=true`) и `/statistic`.
6. Свежий verify только после close/ready:
   ```sh
   sh tools/run-testops.sh verify --execution run-ni_5bvnc \
     --online --transport rest
   ```
   Для bind ожидаются точные шесть passed, project/launch, полная
   пагинация, согласованные case IDs и отсутствие missing/foreign/hidden/
   retries/duplicates.
7. После устойчивого `sent`/`uploaded` повтор той же upload-команды —
   только как проверка локального блокирования, согласно общему заданию 18.

## 8. Ограничения

- Права записи токена не проверены; read-only access не доказывает успех
  будущего create/upload/close.
- CLI `test-case list` возвращает bare array без page metadata, а
  `launch list` имеет лимит по умолчанию; полнота выше опирается на REST
  Page-ответы `testcase`/`launch`, а не на длину массива.
- REST testcase list не отдавал `projectId` в элементе страницы; состав
  inventory доказан project-scoped endpoint'ом, а принадлежность каждого
  из шести ID — отдельным `GET /api/testcase/{id}` с `projectId=5444`.
- Снимок свежий на 12:28:41Z, но не блокирует параллельные серверные
  изменения: исполнитель публикации должен перепроверить состояние сразу
  перед write.
- Локальные state/package `run-ni_5bvnc` этим поручением не
  перепроверялись и не изменялись; это остаётся шагу исполнителя 18A/18.

## 9. Проверки и evidence

- Probe: `.venv/bin/python artifacts/testops-preflight/18b-20261115T122510Z/probe.py`
  → exit 0, `PREFLIGHT_OK`.
- Evidence: `probe.py`, `summary.json`, `project.json`, `allurectl.json`,
  `case-inventory.json`, `case-checks.json`, `launch-search.json`,
  `old-launch-57316.json`, `openapi-page-endpoints.json`, `secret-scan.json`
  — только allowlist metadata, UTC, команды, коды, ID и счётчики.
- Внешних сущностей не создавалось; единственный POST — token exchange
  для read-only JWT. Секреты, JWT, headers и сырые ответы не сохранялись.
- Secret scan по 9 файлам evidence: значение `ALLURE_TOKEN` — 0 hits,
  JWT pattern — 0 hits.
- `git diff --check` — exit 0.
