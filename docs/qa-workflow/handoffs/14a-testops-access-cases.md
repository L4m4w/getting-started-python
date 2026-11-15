# 14A: Read-only доступ к TestOps и поиск кейсов CAT-UPD-VAL

Дата: 2026-11-14. Статус: **ready**.
Область агента 14A: аутентификация, доступ к проекту 5444, allurectl,
поиск кейсов. Контракт launch/results — зона агента 14B, здесь
не исследовался (один `launch list` использован только как контроль
непустоты проекта).

Все вызовы — read-only GET через `allurectl 2.24.0`
(`/Users/zenalark/.local/bin/allurectl`, SHA-256 записан в handoff 11,
бинарь не менялся). Никаких create/upload/watch/auth login/resolve;
локальный state в `artifacts/testops/` не тронут; `~/.allure/` не создан.
Токен передан только через `ALLURE_TOKEN` в env процесса, загружен
`tools.testops.load_environment()` (корневой `.env`, exported env
в приоритете — проверено поведение: значения из `.env` подхватились,
`ALLURE_ENDPOINT`/`ALLURE_PROJECT_ID` в env не заданы).

## 1. Аутентификация и доступ к проекту

| Проверка | Команда (без env) | Результат |
| --- | --- | --- |
| Версия | `allurectl --version` | exit 0, `allurectl version 2.24.0` |
| Токен в env | `load_environment()` + `os.environ` | присутствует (значение не печаталось) |
| Проект | `allurectl --endpoint https://allure.qa.guru -o json project get 5444` | exit 0 → `id=5444, name="ai_project_Larkin_EA"` |
| Список проектов | `allurectl ... -o json project list` | exit 0 → 95 проектов, 5444 присутствует |

**Вывод: токен валиден, чтение проекта 5444 подтверждено.**
95 видимых проектов — широкий read-scope токена на общем учебном
инстансе. Доступ на чтение **не** доказывает прав на запись;
write-scope к 5444 не проверялся и не заявляется.

Сигнатуры ошибок (проверены контрольными вызовами, см. §4):

| Ситуация | exit | stderr (сигнатура) |
| --- | --- | --- |
| Токен отсутствует | — | блок до вызова (`_require_network` в tools/testops.py, exit 69) |
| Токен отклонён | 1 | `oauth2: cannot fetch token … {"status":401,"message":"auth.bad-token"}` |
| Проект недоступен/несуществует | 1 | `GET /api/rs/project/<id>: 403 Forbidden` (404 не выдаётся — "нет проекта" и "нет доступа" неразличимы) |
| Сеть недоступна | — | `client.run` → `timeout`/`launch_error` (на живом инстансе не воспроизводилось) |

## 2. Поиск кейсов CAT-UPD-VAL-001–006

Запросы (AQL из `tools/testops.py:AQL_SCENARIO_SEARCH`):

```sh
allurectl --endpoint https://allure.qa.guru -o json test-case list \
    --project-id 5444 -q 'name ~= "CAT-UPD-VAL"'    # exit 0 → []
allurectl ... test-case list --project-id 5444 \
    -q 'name ~= "CAT-UPD-VAL-"'                    # exit 0 → []
```

| Scenario ID | Вердикт |
| --- | --- |
| CAT-UPD-VAL-001 | поиск завершён, совпадений нет |
| CAT-UPD-VAL-002 | поиск завершён, совпадений нет |
| CAT-UPD-VAL-003 | поиск завершён, совпадений нет |
| CAT-UPD-VAL-004 | поиск завершён, совпадений нет |
| CAT-UPD-VAL-005 | поиск завершён, совпадений нет |
| CAT-UPD-VAL-006 | поиск завершён, совпадений нет |

Отсутствие совпадений заявляется после **полного** поиска:
контроли ниже показывают, что проект заведомо пуст и механизм
запросов работает. Постоянные bindings не назначались, кейсы не
создавались — согласно контексту, синхронизация TestOps ещё не
выполнялась ни одним агентом, пустой проект согласуется с этим.

## 3. Полнота поиска и пагинация

- `test-case list` не имеет `--size`/`--page` flags (проверено по
  `--help`); ответ `-o json` — **единый bare-массив** без обёртки
  (`content`/`totalElements` отсутствуют): сервер возвращает все
  совпадения одним списком, пагинация для этой команды не применима.
- Контроль полноты: `test-case list -q 'true'` → 0 элементов;
  `-q 'id >= 0'` → 0 элементов. Проект содержит **ноль** кейсов —
  усечь нечего.
- Контроль исполнения AQL: `-q 'this is %%% invalid'` → exit 1,
  stderr `Error: GET /api/rs/testcase/__search: 400 invalid.aql`.
  Сервер реально парсит запросы: exit 0 + `[]` на валидном AQL —
  настоящее «нет совпадений», а не тихий сбой.
- Контроль непустоты доступа: `project list` вернул 95 элементов
  одним массивом — клиентская усечённость JSON-вывода исключена.
- `launch list` (только sanity): имеет flag `--size` (default 10) —
  у этой команды пагинация есть; контракт в зоне 14B.
- Точное сопоставление: вердикты считались regex
  `CAT-UPD-VAL-00N(?![0-9])`, исключающим ложное `CAT-UPD-VAL-0010`
  (см. несовместимость №2 ниже).

## 4. Фактические CLI/API/JSON-контракты (verified live)

| Вызов | exit | Формат stdout |
| --- | --- | --- |
| `project get <id>` | 0 | **list** `[{"id":N,"name":str,"isPublic":bool}]` — не dict |
| `project list` | 0 | list `[{id,name,isPublic}]`, 95 элементов |
| `test-case list -p <id> -q <aql>` | 0 | bare list; элементов не было, item schema не проверена |
| `launch list -p <id> -q true --size 5` | 0 | bare list `[]` |
| ошибка (401/403/400) | 1 | stderr `Error: <METHOD> <path>: <status> <reason>` + usage dump; stdout пуст |

API-пути из stderr: `GET /api/rs/project/<id>`,
`GET /api/rs/testcase/__search` — полезно для будущего REST-probe
(тело запроса `__search`, видимо, формируется из AQL).

## 5. Несовместимости client.py (код не менялся)

1. **`launch_list_args` без `--size`.** `launch list` режет выдачу
   до 10 (default). `infrastructure/reporting/testops/client.py:117-119`
   строит команду без `--size` — verify над списком launches > 10
   будет слеп к хвосту. Пример: `allurectl launch list -p 5444 -q true`
   при 15 launches вернёт 10. Предложение: передавать явный `--size`
   (после подтверждения семантики страниц агентом 14B).
2. **Подстрочное совпадение в `cmd_resolve`.**
   `tools/testops.py:286` — `scenario_id in case["name"]`:
   `CAT-UPD-VAL-001` сматчит `…-0010`. Предложение: граница номера
   `re.compile(re.escape(sid) + r"(?![0-9])")` (использована в probe).
3. **`parse_cases` совместим, но item schema не проверена.**
   Фактический root — bare list (`_json_payload` обрабатывает);
   поля `id`/`name` элементов в живых данных не видны (0 кейсов).
   По аналогии с `project` items (`id`,`name`) вероятны, но первый
   непустой поиск должен подтвердить схему.
4. **`project get` отдаёт list, не dict.** Для `client.py` helper'а
   нет — не конфликт, но если добавлять `parse_project`, принимать
   list-of-one.
5. **Классификация 403.** «Проект не существует» и «нет доступа» —
   оба `403 Forbidden`; `classify`-логике нельзя выдавать 404-семантику.
   Формат ошибки — `Error: <METHOD> <path>: <status> <reason>` в stderr.
6. `resolve` пишет state (by design); для чистого read-only поиска
   использовались прямые вызовы. При желании — отдельный
   `--dry-run`/no-save режим `cmd_resolve`.

Совместимость подтверждена: порядок global flags (`--endpoint`,
`-o json` до subcommand), `case_list_args`, `_json_payload` на
bare list, обработка nonzero exit в `cmd_resolve`.

## 6. Evidence

`artifacts/testops-readonly/14a-20261114T155451Z/`:

- `probe.py` — точный сценарий всех основных вызовов;
- `summary.json` — version/project/два поиска/вердикты (UTC, argv,
  exit codes, wrapper keys, id/name);
- `control.json` — контроли: `test-case list -q true`, `id >= 0`,
  `project list`, `launch list --size 5`, invalid AQL,
  bad-token/missing-project/foreign-project сигнатуры.

Все файлы фильтрованы по allowlist (UTC/argv/exit/id/name/счётчики);
сырые ответы и токен не сохранялись.

## 7. Готовое поручение на исправления

1. `client.py`: явный `--size` в `launch_list_args` (сверить семантику
   с результатами 14B).
2. `tools/testops.py`: ужесточить совпадение scenario ID в `cmd_resolve`
   boundary-regex (защита от `…-0010`).
3. При первом непустом поиске подтвердить item schema `id`/`name` в
   `parse_cases`.
4. Учесть 403-not-404 семантику `project get` при будущей
   классификации ошибок.
5. Кейсов CAT-UPD-VAL-001–006 в проекте 5444 нет: маршрут `isolate`
   (авто-создание при разрешённом upload) или ручное создание —
   решение координатора, bindings свободны.
