# 16B: read-only preflight TestOps и контракт публикации

Агент: `16B`. Дата/время проверок: **2026-11-15T11:30–11:34Z**.
Статус: **ready** — read-only preflight выполнен, команды upload/close и
порядок восстановления подтверждены настолько, насколько это возможно без
внешней записи. Публикация сама не выполнялась и не разрешалась.

Область соблюдена: этот handoff и
`artifacts/testops-preflight/16b-20261115T113017Z/`
(`probe.py`, `summary.json`, `allurectl-help.txt`,
`rest-close-endpoint.json`). `artifacts/testops/` не изменялся и не
блокировался — там параллельно работает 16A; состояния читались пассивно,
без lock и без записи. Внешних записей, create/upload/close/watch,
CLI plan/status/package/resolve/verify не было.

## 1. Окружение и доступ

- `.env` загружен через `tools.testops.load_environment()`;
  `ALLURE_TOKEN` присутствует (значение не выводилось/не сохранялось).
  `ALLURE_ENDPOINT` и `ALLURE_PROJECT_ID` в env не заданы → эффективные
  endpoint `https://allure.qa.guru`, project **5444** — совпадают с
  поручением. Несоответствий нет, блокера нет.
- `allurectl 2.24.0` — `/Users/zenalark/.local/bin/allurectl`,
  sha256 `5928e200ba7e82e7c2b13c4d22d9ec1fd415e932445422b9253acfd5f62c1fba`
  — идентичен записанному в handoff 11, бинарь не менялся.
- Token exchange `POST /api/uaa/oauth/token` → **HTTP 200**: токен
  валиден для чтения. **Права записи не проверены и не заявляются** —
  первый write-вызов (`launch create`) может вернуть 401/403.

## 2. Живой снимок проекта 5444 (fresh, не кэш 14-й волны)

Все вызовы — read-only GET через `probe.py` (client.py args + REST).

| Проверка | Команда/запрос | Результат |
| --- | --- | --- |
| Проект | `allurectl project get 5444` | exit 0 → `id=5444, name="ai_project_Larkin_EA"` |
| Пилотные кейсы | `test-case list -p 5444 -q 'name ~= "CAT-UPD-VAL"'` | exit 0 → 0 кейсов |
| Контроль полноты кейсов | `test-case list -p 5444 -q 'id >= 0'` | exit 0 → **всего 0 кейсов** |
| Все launches | `launch list -p 5444 -q true --size 500` | exit 0 → 0 launches |
| Пилотные launches | `launch list -p 5444 -q 'name ~= "CAT-UPD-VAL"'` | exit 0 → 0 |
| REST-контроль | `GET /api/launch?projectId=5444&page=0&size=10` | HTTP 200, `totalElements=0`, `last=true` |

Полнота поиска доказана: проект **пуст** (0 кейсов, 0 launches —
двумя независимыми путями: CLI и REST). Усекать нечего; граница ID
не нужна, но применённый regex `(?<![A-Za-z0-9_-])SID(?![A-Za-z0-9_-])`
исключает ложное `…-0010` на случай появления данных.

## 3. Вердикты по сценариям

| Scenario | Вердикт | Кандидат |
| --- | --- | --- |
| CAT-UPD-VAL-001 | отсутствует | — |
| CAT-UPD-VAL-002 | отсутствует | — |
| CAT-UPD-VAL-003 | отсутствует | — |
| CAT-UPD-VAL-004 | отсутствует | — |
| CAT-UPD-VAL-005 | отсутствует | — |
| CAT-UPD-VAL-006 | отсутствует | — |

Кандидатов нет; bindings не назначались. **Рекомендация: `isolate`** —
согласуется с wave 9/10 и поручением 16: при пустом проекте кейсы
создаются сервером по сигнатурам пакета после close launch.
`bind` сейчас невозможен (не к чему привязывать). Появление частичного
набора до публикации — повторный needs_decision.

## 4. Подтверждённый инструментальный контракт

### Сопоставление help ↔ client.py (всё совместимо)

| client.py | argv | help 2.24.0 |
| --- | --- | --- |
| `launch_create_args` | `launch create --project-id P --launch-name N` | `-p/--project-id`, `--launch-name` — есть |
| `upload_args` | `upload --project-id P --launch-id L <dir>` | `--project-id`, `--launch-id int`, позиционный `<directory>` — есть |
| `launch_get_args` | `launch get <id>` | позиционный `<launch-id>` — есть |
| `launch_list_args` | `launch list --project-id P -q <aql>` | есть; `--size` default **10** — усечение из handoff 14A подтверждено |
| `case_list_args` | `test-case list --project-id P -q <aql>` | есть; `--size`/`--page` отсутствуют — единый массив |

### Ключевые выводы для публикации

1. **`launch close` существует**: `allurectl launch close <launch-id>`
   (global flags `--endpoint`, `-o json` — до subcommand). client.py и
   CLI его не обёртывают → close — отдельный ручной write-шаг вне
   `perform_upload`, требует собственной авторизации в поручении.
2. **upload не создаёт второй launch при `--launch-id`**: help разводит
   `--launch-id` («Launch to upload for») и `--launch-name` («Launch
   name for **create**»). client.py всегда передаёт `--launch-id`
   записанного launch. (Семантика по help; live не проверено.)
3. **Автоматического close у upload не зафиксировано**: в help нет
   флага; документация описывает close вручную/по auto-close policy
   проекта; кейсы создаются **только после закрытия** launch
   (docs.qameta.io test-cases/launches-overview). Исходники allurectl
   закрыты (репозиторий = только docs). Рабочая модель: после `sent`
   launch остаётся открытым → обязательный явный close; факт проверять
   read-only (`closed` в `GET /api/launch/{id}` / `LaunchDto.closed`,
   поле `autoclose` — проектная политика, на пилот не рассчитывать).
4. **Документированный REST close**: `POST /api/launch/{id}/close` →
   **204 No Content** (OpenAPI 3.1.0, сервис `527u01`, проверено по
   живому `/api-docs` сегодня). Подтверждённая альтернатива close —
   тоже write, только по отдельной авторизации.
5. **Машиночитаемый признак обработки**: `GET /api/launch/{id}/progress`
   → `{ready}`; колонка `Ready` есть и в `--format` табличных команд,
   но JSON-форма `launch get` непроверена — источник истины для
   ожидания — REST progress.
6. `launch create -o json` → формат stdout не проверен live
   (`parse_launch_id` принимает list/dict с `id`); нечитаемый ID —
   штатная ветка `unknown` lifecycle.
7. Подтверждённый таймаут upload в CLI — `UPLOAD_TIMEOUT_S=1800` с
   (subprocess), сам `allurectl --timeout` default `10h` — убивает
   раньше subprocess, результат — `unknown`, не retry-safe.

## 5. Точный план одной публикации (фаза B, по отдельному разрешению)

Предусловие (выполнено 16A, проверено пассивно): state `run-5tsmzg1d`
schema 2, `pending`, attempts=0, launch=null, isolate-пакет
`a6f1cdddabfa4608…` (40 файлов, 6 результатов) с
input/assignments digests. Перед write — повторная сверка state/digests.

1. **Upload** (один раз, под штатным `--execute`):
   ```sh
   sh tools/run-testops.sh upload --execution run-5tsmzg1d --execute \
       --launch-name 'CAT-UPD-VAL run-5tsmzg1d <UTC-метка>'
   ```
   CLI сам делает `launch create` → `upload --launch-id`; отдельный
   create не нужен. Exit 0 → статус `sent` (не `uploaded`!).
   Уникальность имени важна для recovery-поиска.
2. **Принадлежность launch** (read-only): `GET /api/launch/{id}` →
   `projectId=5444`, фиксация `closed`/`autoclose`, launch URL
   `https://allure.qa.guru/launch/<id>`.
3. **Close** (только если `closed=false`, согласованная команда):
   ```sh
   allurectl --endpoint https://allure.qa.guru -o json launch close <id>
   ```
   Исход проверяется перечитыванием `closed` (сам exit не доказательство).
   Фallback по отдельной авторизации: `POST /api/launch/{id}/close` → 204.
4. **Ожидание обработки** (read-only, ≤10 мин, шаг ~15 с):
   `GET /api/launch/{id}/progress` → `ready=true` +
   `/statistic` непустая. Истечение лимита → needs_decision, state
   остаётся `sent`, повторного upload нет.
5. **Verify**: `sh tools/run-testops.sh verify --execution run-5tsmzg1d
   --online --transport rest` → в isolate ожидаем inconclusive (exit 75)
   с `confirmation.checks.candidates` — это кандидаты ID, не bindings.
   Сверка шести ID → согласование → `assign` → повторный REST verify →
   `confirmed` → `uploaded`.
6. **Идемпотентность** (после устойчивого sent/uploaded): повтор той же
   upload-команды → ожидаемый локальный **exit 69 до транспорта**
   (`decide_upload` блокирует); attempts/launch/пакет неизменны.

Exit-коды CLI: 0 — локальная операция/sent; 2 — argparse; 69 — блок;
75 — неопределённый/неполный; 127 — процесс не запустился; 130 — прерывание.
allurectl ошибки — exit 1, `Error: <METHOD> <path>: <status>` в stderr;
401 bad-token, 403 проект недоступен/нет прав, 404 launch missing,
400 invalid AQL.

**Неподтверждено:** права записи токена, живое создание кейсов из
isolate-пакета, точная серверная дедупликация по сигнатуре, поведение
`ready`/`hidden`/`in_progress` на непустых данных, автозакрытие upload.
Шесть серверных кейсов по offline-пакету не обещаем.

## 6. Recovery-матрица

| Исход | State | Read-only диагностика | Условие остановки |
| --- | --- | --- | --- |
| create: nonzero/timeout/interrupt или exit 0 без читаемого ID | `unknown` (launch может существовать без ID) | `launch list -p 5444 -q 'name ~= "<уник. имя>"'` + REST page-walk `/api/launch?projectId=5444`; кандидат = точное имя + окно createdDate | Нет кандидата или >1 → needs_decision. Никогда не повторять create (второй launch). Adoption — отдельное поручение |
| upload: nonzero exit / timeout / interrupt | `unknown` (возможна частичная запись) | RestProbe snapshot записанного launch: страницы `/api/testresult` — частичный набор → partial/contradiction; 0 строк + `ready=false` → обработка идёт | Любой признак частичной записи → needs_decision, resend заблокирован навсегда для этого launch |
| `sent`, обработка задерживается | `sent` | `progress.ready` + `/statistic` по таймеру; `ready=false` при пустой статистике = inconclusive, не empty | Лимит ожидания → needs_decision; state сохранён, новых upload нет |
| empty при closed+ready | `empty` → `unknown` | Полный REST snapshot (пагинация доказана) + ручная сверка в UI | Пустой launch не доказывает отсутствие batch → resend запрещён; только ручное разрешение |
| close: исход неизвестен (nonzero/timeout) | state не меняется (вне lifecycle) | Перечитать `GET /api/launch/{id}` → `closed=true` значит close состоялся | `closed=false` → одно повторение той же close по той же авторизации; подтвердить не удалось → needs_decision, дальнейших write нет |
| `failed` (только доказанный pre-write, `launch_error`) | `failed` | upload.log + отсутствие внешних вызовов | Единственный статус, где `--retry` вообще рассматривается — отдельным поручением, с тем же записанным launch ID |

Блокировки resend: `in_progress`, `unknown`, `sent`, `uploaded` —
всегда. `empty` не открывает retry. `adopt_launch`,
`resolve_in_progress`, `mark_upload_confirmed`, отдельный execution
для обхода state — не применять без отдельного поручения.

## 7. Замечания для координатора (код не менялся)

- `client.launch_list_args` без `--size` — усечение 10 подтверждено
  help; recovery-поиск launch вести AQL-фильтром по имени или REST
  page-walk, не общим списком.
- Close вне lifecycle/CLI: факт и время close не попадут в
  `upload.attempts` — фиксировать в handoff публикации вручную
  (UTC + результат перечитывания `closed`).
- `verify` требует `upload.package_sha256 == package.sha256` и
  записанный launch — до close/verify ничего в пакете не пересобирать.

## 8. Проверки

- `git diff --check` — exit 0. Unit/collection не повторялись
  (реализация не менялась).
- Evidence-файлы — только allowlist metadata; чужие сущности не
  перечислялись (контроль — счётчиками).
- Текущее состояние `artifacts/testops/run-5tsmzg1d` на 11:34Z:
  schema 2, pending, isolate-пакет собран — читано пассивно;
  фактическое состояние перед публикацией перепроверяет исполнитель фазы B.
