# Передача результата: проверяемая модель состояний TestOps upload/verify

Агент: `13`. Дата: 2026-11-14. Статус: `needs_decision` — модель lifecycle
проверена offline; интеграцию в CLI и решения по точкам ниже выполняет
координатор.

Исправлена модель состояний и восстановления TestOps upload/verify по
замечаниям координации (wave 6, пункты P1): слабый verify по наличию
launch, слепой retry после ненулевого upload, потеря launch при нечитаемом
ID, молчаливый сброс повреждённого state, отсутствие execution lock.
Область записи соблюдена: `state.py`, `client.py`, новые `lifecycle.py`,
`tests/unit/test_testops_lifecycle.py`, `test_data/consts/testops_lifecycle.py`,
этот handoff. `tools/testops.py`, `results.py`, существующие тесты и общие
документы не менялись; файлы агента 12 не трогались. Живых запросов к
TestOps, upload, Docker/Gradle/API, чтения/вывода токена не было.

## Модель фаз и исходов (schema 2)

Статусы `state.upload.status`:

| Статус | Смысл | Дальнейшие действия |
| --- | --- | --- |
| `pending` | внешних записей не было, launch не записан | upload разрешён (с пакетом) |
| `in_progress` | попытка внутри внешней операции; `phase` = `launch_create` или `upload` | блокирует всё; после падения процесса — только явный `resolve_in_progress` → `unknown` |
| `sent` | `upload` завершился exit 0: батч доставлен, серверная обработка полного набора **не** подтверждена | повторная отправка заблокирована; только verify |
| `failed` | доказанный отказ/дозаписный сбой: отказ `launch create`, `launch_error` (процесс не стартовал), verify доказал пустой launch | retry только явный (`retry=True`/`--retry`); с записанным launch повтор идёт **в тот же** launch, без него — новый create |
| `unknown` | неопределённый исход: timeout, прерывание, нечитаемый ответ после возможной записи, ненулевой exit батча (частичное принятие возможно), противоречие/пропажа launch при verify | блокирует всё, включая `--retry`; сначала verify или ручное разрешение |
| `uploaded` | терминал: launch ID + проект + полный ожидаемый набор результатов и bindings подтверждены сервером (автоматически или записанным ручным подтверждением) | повтор невозможен никогда |

Различие исходов: `failed` = доказанный отказ; `unknown` = неизвестный
результат (внешняя запись могла частично пройти); `sent` = доставлено, но
не подтверждено; `uploaded` = подтверждённый успех. Никакой переход не
теряет записанный launch: `abandon_launch` переносит его в аудит
`upload.abandoned`, а не удаляет.

Границы записи на диск: `begin_upload_attempt` (in_progress) и
`record_launch` сохраняются **до** соответствующих внешних вызовов —
падение процесса оставляет правдивый маркер. Каждая завершённая попытка
добавляется в `upload.history` (фаза, статус, exit, времена, detail).

## Верификация uploaded

`perform_verify` подтверждает только полную цепочку:

1. `launch get <recorded_id>` — найденная сущность обязана иметь тот же id,
   что записан в state (переданный `--launch-id`, отличающийся от
   записанного, — contradiction, а не подмена).
2. Проект: `projectId` из ответа, иначе запасной `launch list --project-id
   P -q 'id = N'`; несовпадение — contradiction, нечитаемо — inconclusive.
3. Набор результатов: per-status статистика launch (колонки
   Passed/Failed/Broken/Skipped — см. источники) против ожидаемой сводки
   из `scenarios`. 0 → `empty` (статус → `failed`, retry в тот же launch);
   меньше → `partial`; больше ожидаемого → `overdelivered` → contradiction.
4. Bindings: только через per-result probe (`transport.list_launch_results`),
   сверка имени `SID: …`, статуса и `test_case_id` с ожидаемыми
   `testops_id` (bind) или наличием привязки (isolate).

Вердикты: `confirmed` → `uploaded`; `empty` → `failed` (retry-safe);
`partial` → статус сохраняется + evidence; `inconclusive`/`unreachable` →
статус не меняется; `missing`/`contradiction` → `unknown` + диагностика.
Всё, что не доказано, остаётся неопределённым — автоматического успеха
по одному факту существования launch больше нет.

**Честное ограничение:** allurectl 2.24.0 не имеет per-result чтения
(`allurectl --help`: только auth/ci/job/job-run/launch/project/test-case/
upload/watch). Транспорт на чистом allurectl даст bindings `inconclusive`,
значит `confirmed` автоматически недостижим — это осознанно: итоговое
`uploaded` тогда требует записанного ручного подтверждения (UI-сверка
launch: N результатов `CAT-UPD-VAL-00X: …` с ожидаемыми статусами и
привязками к кейсам) через `mark_upload_confirmed(method="manual")`.
REST `GET /api/rs/testresult?launchId=` — официально задокументирован
только в Swagger конкретного инстанса (`/swagger-ui.html`, Report
Service); форму ответа offline проверить негде, поэтому HTTP-путь
намеренно не реализован — `parse_launch_results` и probe-интерфейс уже
готовы, решение о подключении REST за координатором после сверки живого
ответа.

## Execution lock

`lifecycle.ExecutionLock(state_dir, operation)` — файл
`artifacts/testops/<execution>/execution.lock` с `{pid, token, operation,
acquired_at}`, атомарный `O_CREAT|O_EXCL`. Охватывает весь цикл
load → решение → внешняя операция → сохранение и в `perform_upload`, и в
`perform_verify`. Второй держатель получает `LockHeldError` с pid/операцией/
временем владельца. Lock мёртвого pid забирается как mutex — но **не**
даёт обойти сохранённый `in_progress`/`unknown`: после захвата state
загружается и статус блокирует сам по себе. Повреждённый lock —
понятный отказ с инструкцией ручного удаления. `release` удаляет файл
только при совпадении token (чужой lock не стирается).

## Совместимость schema 1

- `load_state` возвращает `None` только при отсутствии файла; битый JSON,
  не-объект и нечитаемый файл — `StateCorruptError`; неизвестная версия/
  статус — `StateSchemaError`. Тихого создания pending поверх истории
  больше нет (`load_state_or_error` — вариант с кортежем для CLI).
- Миграция v1→v2 в памяти: поля/привязки/launch/attempts сохраняются.
  v1 `failed` **с записанным launch** → `unknown` (возможное частичное
  принятие — слепой retry закрыт); без launch → `failed`. `unknown`,
  `uploaded`, `in_progress`, `pending` сохраняются; мигрированный
  `uploaded` помечается `confirmation.method="migrated"` (подтверждён
  только exit-кодом CLI, без серверной сверки). Файлы
  `artifacts/testops/*/state.json` в работе **не** мигрировались —
  запись schema 2 произойдёт только при следующем save от вызвавшего
  его CLI.

## Публичные интерфейсы

Сохранены и совместимы с текущим `tools/testops.py`: `new_state`,
`state_path`, `save_state`, `record_results`, `set_binding`,
`mark_ambiguous`, `unresolved_ids`, `record_package`, `can_upload`
(+ статус `sent`), `mark_upload_started`→`begin_upload_attempt`,
`mark_upload_finished`→`complete_attempt`, `record_launch` (форма записи
schema 1 для create-пути сохранена — существующий тест сравнивает dict).

Новое в `state.py`: `SCHEMA_VERSION=2`, `ATTEMPT_PHASES`,
`CONFIRMATION_VERDICTS`, `StateCorruptError`, `StateSchemaError`,
`migrate_state`, `load_state_or_error`, `expected_scenarios`,
`expected_stats`, `begin_upload_attempt`, `set_attempt_phase`,
`complete_attempt`, `adopt_launch`, `abandon_launch`,
`resolve_in_progress`, `record_confirmation`, `mark_upload_confirmed`.

Новое в `client.py`: `launch_list_args`, `parse_launch` (id/name/
projectId/статистика — защитный разбор: нечитаемое → inconclusive, не
угадывание), `parse_launch_results` (для будущего REST/probe-транспорта).

Новое в `lifecycle.py`: `ExecutionLock`, `LockHeldError`,
`decide_upload`, `perform_upload`, `perform_verify`, dataclass-результаты
`UploadRun`/`VerifyRun`/`ExternalCall`, константы фаз/исходов/вердиктов.
Транспорт инъецируется (duck-typing): `create_launch`, `upload_package`,
`get_launch`, `list_launches`, `list_cases`, опционально
`list_launch_results(endpoint, launch_id)` → list[dict] | `CommandResult`
| None (None = нет пути чтения → bindings inconclusive).

## Официальные источники

- `allurectl 2.24.0 --help` (локально): набор команд без per-result чтения;
  `launch get/list/create --format` документирует колонки `ID, Name, Tags,
  Passed, Failed, Broken, Skipped, Ready`; `upload` — батч `--size`/`--concurrency`
  → частичное принятие при обрыве реально; `launch list` требует
  `--project-id` и принимает `-q` AQL.
- `docs.qameta.io/reference/ecosystem/allurectl/` — upload workflow,
  local mode создаёт один launch; параметры через env.
- `github.com/allure-framework/allurectl` `cookbook.md` — upload после
  завершения тестов, env-переменные; релиз `1.20.0` — статистика launch.
- `docs.qameta.io/reference/api/` — публичный API только на чтение/
  управление; upload — только через поддерживаемые инструменты; Swagger
  UI на инстансе — источник полей ответа.
- `docs.qameta.io/use-testops/test-plans-and-launches/launches-overview/` —
  обработка результатов launch при закрытии (возможная задержка статистики —
  учтено в тексте `empty`-вердикта).

JSON-схема `launch get -o json` и REST `testresult` живым запросом не
проверялись (токена нет, запросы запрещены): разборы защитные, всё
непрочитанное → inconclusive.

## Проверки и evidence

| Команда | Exit | Итог |
| --- | --- | --- |
| `sh tools/run-tests.sh group unit` | 0 | **146 passed**, 0 failed — включая 27 новых lifecycle-тестов и существующий набор; `artifacts/harness/run-wqzvyg8m/` |
| `sh tools/compile-tests.sh` | 0 | 161 collected |
| pytest --collect-only нового файла | 0 | 27 тестов |

Покрытие обязательных сценариев (`tests/unit/test_testops_lifecycle.py`):
пустой launch не подтверждает; неверный launch ID/проект — contradiction/
missing → unknown; частичный набор — partial, статус сохраняется;
create exit 0 + нечитаемый ID — unknown без второго launch; timeout и
KeyboardInterrupt на обеих фазах — unknown/interrupted с сохранённым
launch; ненулевой upload exit — unknown, блок даже с retry; retry после
доказанного failed идёт в записанный launch; блок для uploaded/unknown/
in_progress; повреждённый state — явное исключение без перезаписи;
миграция schema 1 (failed+launch→unknown, uploaded/unknown сохраняются);
конкурентный захват lock — отказ, stale-pid забирается без обхода
in_progress, битый lock — отказ; доказанный успех — `sent` → verify с
полным probe → `uploaded`; in_progress сохраняется до первого внешнего
вызова (порядок persist проверен снимками).

## Ограничения

- Автоматический `uploaded` недостижим транспортом на чистом allurectl —
  нет per-result чтения; предусмотрен ручной `mark_upload_confirmed` после
  UI-сверки. REST-probe — решение координатора после проверки Swagger
  инстанса.
- `empty`-вердикт: статистика может отставать от загрузки; текст статуса
  требует убедиться в завершении серверной обработки перед retry.
- Lock на живость pid — POSIX (`os.kill(pid,0)`); кроссплатформенность
  Windows не требовалась и не проверялась.
- Проверки проекта через `launch list -q 'id = N'`: поле `id` в launch-AQL
  правдоподобно, но без живого запроса не подтверждено — при ошибке
  команда даёт inconclusive, а не ложный ответ.
- `tools/testops.py` не изменён и всё ещё содержит старый слабый
  upload/verify — до интеграции им пользоваться нельзя.

## Точные изменения для интеграции (координатор)

1. `cmd_upload` → `lifecycle.perform_upload(state_dir, transport,
   launch_name=..., timeout_s=options.timeout, retry=options.retry)`.
   Транспорт — тонкий адаптер над `client.run`: `create_launch` →
   `launch_create_args`, `upload_package` → `upload_args`,
   `get_launch` → `launch_get_args`, `list_launches` → `launch_list_args`,
   `list_cases` → `case_list_args`; `list_launch_results` не
   реализовывать (None → bindings inconclusive). `run.calls` писать в
   `upload.log`. Маппинг исходов: `sent` → 0 («доставлено, требуется
   verify»), `failed` → сохранить exit-код allurectl как раньше,
   `unknown` → 75, `interrupted` → 130, `blocked` → 69.
2. `cmd_verify` → `perform_verify`. Вердикты: `confirmed`/`empty` → 0
   (empty — «решено к retry»); `partial`/`inconclusive`/`unreachable` → 75;
   `missing`/`contradiction` → 69 (ручное разрешение).
3. Порядок lock: оба выполнения должны идти **внутри** одного
   `ExecutionLock` — acquire до `load_state`, release после последнего
   `persist` (perform_* уже делают это; CLI не должен грузить state вне
   lock и затем вызывать perform_*, иначе решение расходится с файлом).
   `resolve`/`assign`/`package` тоже рекомендуется обернуть тем же lock.
4. `_load_or_new`/`_require_state`: ловить `StateCorruptError` → печать и
   `69`, никогда не `new_state` поверх нечитаемого файла.
5. Новые подкоманды для восстановления (имена — предложение):
   `adopt-launch --execution X --launch-id N` → `adopt_launch`
   (восстановление после create exit 0 с нечитаемым ID: найти launch
   через `launch list -p P`/UI и зафиксировать его ID вместо создания
   второго); `resolve-attempt --execution X --note "..."` →
   `resolve_in_progress`; `abandon-launch --execution X --reason "..."` →
   `abandon_launch` (после удаления/признания orphan на сервере);
   `confirm-uploaded --execution X --note "..."` →
   `mark_upload_confirmed(method="manual")` после UI-сверки.
6. Адаптация `tests/unit/test_testops.py::test_verify_resolves_unknown_upload`
   (сам файл я не менял): verify по факту существования launch больше не
   должен давать `uploaded`; ожидание переписать под новую модель —
   verify без статистики/bindings оставляет `unknown`/`sent` либо гнать
   сценарий через `perform_verify` с подменённым транспортом.
7. Загрузка `.env` — отдельная задача координатора (P2 wave 6), здесь не
   делалась.
8. Каталог компонентов (`knowledge/components/infrastructure.md`,
   `consts.md`): добавить записи про `lifecycle.py`,
   `test_data.consts.testops_lifecycle` и новые функции `state/client` —
   общие файлы вне моей области.
9. `knowledge/integrations/testops.md` — заменить раздел «Повторы и сбои»
   на модель выше и описать `sent`/`unknown`/`empty`-пути и ручную сверку.

## Следующее поручение исполнителю синхронизации

После интеграции CLI: `upload --execute` → `sent`; `verify --online` →
confirmed/partial/inconclusive; при inconclusive — ручная сверка launch в
UI и `confirm-uploaded --note`; при `empty` — `upload --retry` (в тот же
launch); при `unknown` — разбирательство через `adopt-launch`/
`abandon-launch`/`resolve-attempt`, а не повтор вслепую.
