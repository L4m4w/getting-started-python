# Передача результата: локальная проверка и isolate-кандидат run-5tsmzg1d

Агент: `16A`. Дата: 2026-11-15. Статус: `ready`.

Локальная часть поручения 16 выполнена: execution `run-5tsmzg1d` проверен,
state мигрирован в schema 2 штатным CLI, isolate-пакет пересобран и проверен
offline integrity-функциями. Пакет — **кандидат**: выбор isolate/bind и
публикация остаются за координатором после отчёта 16B. Внешних обращений,
upload/resolve/verify, назначения case IDs и recovery-операций не было.
`upload.status` остаётся `pending`, `attempts=0`, `launch=null`.

## Inventory до изменений (read-only)

- States в `artifacts/testops/`: `run-5tsmzg1d` и `run-vzsatlfk` — оба
  schema 1, `pending`, `attempts=0`, `launch=null`, endpoint
  `https://allure.qa.guru`, project `5444`. Совпадает с наблюдением wave 10.
- Отчётов 16A/16C, каталога `artifacts/testops-live/`, lock/gate-файлов и
  `upload.log` не было — следов чужой или внешней попытки нет.
- Старый isolate-пакет кандидата (40 файлов) не содержал
  `input_sha256`/`assignments_sha256` — пересборка потребовалась и выполнена.
- Env: `ALLURE_ENDPOINT`/`ALLURE_PROJECT_ID`/`ALLURECTL`/`ALLURE_TOKEN` не
  экспортированы; корневой `.env` не содержит ключей `ALLURE_*` — целевые
  endpoint/project определены только аргументами CLI и совпали с заданием.
- Baseline `run-vzsatlfk` не тронут и не пакетировался.

## Проверка source `artifacts/harness/run-5tsmzg1d`

- `manifest.json` sha256
  `343f317e43ece1a5b72ff1cc688dfe4dc77057e9badfe12296aa981d0cfb2702` —
  совпал с записью wave 10. Schema 2, status completed, exit 0.
- JUnit: `junit.xml` sha256
  `caf402154a7df78491180c3d2ad230a4453dd70334ab665f766df9f62ec4c2e6`;
  6 testcase, все PASS, параметризованные ID CAT-UPD-VAL-001–006.
- `allure-results/`: 40 файлов (6 result, 16 container, 18 attachment).
  Все 6 результатов `passed`; UUID совпадают с `state.scenarios`;
  посторонних/unmapped результатов нет; все ссылки на вложения разрешимы.
- `api-contract-v1`: 15 файлов, `missing=[]`, `changed_during_run=[]`;
  хеши manifest == копии в `sources/` == текущие рабочие файлы.
- Связь с base+patch по `artifacts/integration/catupdval-rerun/`:
  `declared.app_base_sha` = `36674280b6878540a9e88f40aaeedf5dfdd2e6ce`;
  `declared.app_patch_sha256` = `04eb4c87…` = sha256 `base-to-fix.patch`;
  `container_check` performed/running/matches_declared_image = true;
  image `sha256:f496835f…` = `image-ids-fix.txt` и pre/post binding.
- Скан всех 40 файлов source на bearer/JWT/password/token/code_verifier/
  DSN/basic-auth паттерны — находок нет (содержимое не выводилось).

## Выполненные команды (локально, без сети)

```sh
sh tools/run-testops.sh status --execution run-5tsmzg1d                # exit 0
sh tools/run-testops.sh plan --execution run-5tsmzg1d \
  --results artifacts/harness/run-5tsmzg1d/allure-results \
  --endpoint https://allure.qa.guru --project-id 5444                  # exit 0
sh tools/run-testops.sh package --execution run-5tsmzg1d --mode isolate # exit 0
```

Эффективные и записанные в state значения: endpoint `https://allure.qa.guru`,
project `5444`. State после plan — schema 2; upload остался `pending`.

## Итоговые идентификаторы

| Поле | Значение |
| --- | --- |
| execution | `run-5tsmzg1d` |
| input sha256 (results, 40 файлов) | `8a10069a680778c7989eac9e39309cd075e66e7dbdb9d4b40b7b79012b8081d4` |
| assignments sha256 | `727bd91d59dc95ab3417eed2a654b1f7e5f62261fac7e33c813ba535c864dcdc` |
| package sha256 (40 файлов, 6 results) | `a6f1cdddabfa460897b28fb8bd22cbe46bc0e6687489e61f86cbbfaf5e6e87ec` |
| mode | `isolate` |
| state sha256 до | `ed419a8c61bf5481c35b4db2eb006b26a1a384b0650c879c0dea3f6ace5ac1f2` (schema 1) |
| state sha256 после | `c0c09408b261b9caa938d71337e3c6e9e138400979aa22ffc390a95e8964165a` (schema 2) |

Новый пакет байт-в-байт совпал со старым (`diff -r` бэкапа и нового пуст;
digest детерминирован) — пересборка добавила только записанные в state
`input_sha256`/`assignments_sha256`, которых не хватало для pre-upload gate.

## Offline integrity пакета

Через `infrastructure.reporting.testops.results` (без сети):
`verify_source_digest` и `verify_package` — OK; `scan_assignments` по
исходным результатам — отображение 1:1 на шесть сценариев. Для каждого
результата пакета проверена перезапись: `name` с префиксом `SID:`,
`fullName` с суффиксом `[SID]`, пересчитанные `testCaseId`/`historyId`,
сохранённый UUID, `status=passed`, отсутствие `ALLURE_ID` (изоляция).
Набор имён файлов идентичен source; container и attachment файлы
байт-идентичны исходным.

## UUID → scenario → status (пакет)

| UUID | Scenario | Status |
| --- | --- | --- |
| `a98a17e2-14f5-4155-bdb1-e09afa30bd75` | CAT-UPD-VAL-001 | passed |
| `d293e959-8503-491b-a430-9601ea846ff3` | CAT-UPD-VAL-002 | passed |
| `679278d5-711f-4cd0-94af-645fd10ad05b` | CAT-UPD-VAL-003 | passed |
| `a08e7f5a-b69c-4d7c-ad1a-4409134a0504` | CAT-UPD-VAL-004 | passed |
| `c244a385-35cf-4d63-a60b-922c9f51c925` | CAT-UPD-VAL-005 | passed |
| `44a7212b-4e9a-4da0-9ee6-d377feb967db` | CAT-UPD-VAL-006 | passed |

## Изменённые файлы и evidence

- `artifacts/testops/run-5tsmzg1d/state.json` — schema 1 → 2, package
  дополнен `input_sha256`/`assignments_sha256`/`built_at`.
- `artifacts/testops/run-5tsmzg1d/upload-results/` — пересобран штатным
  CLI (содержимое совпало со старым пакетом).
- `artifacts/testops-preflight/16a-20261115T112936Z/` — `state-before.json`,
  `old-package/` + `old-package.sha256`, `state-after.sha256`,
  `verification.txt` (полная сводка проверок).
- Этот отчёт.

## Ограничения и передача координатору

- Живой проект 5444 не проверялся; кейсов в нём по-прежнему может не быть
  (по 14A проект был пуст) — решение isolate/bind после отчёта 16B.
- `ready` означает готовность локального кандидата, не разрешение
  публикации. Upload/close/verify — только по отдельному поручению.
- После этой передачи запись в общий execution state `run-5tsmzg1d`
  прекращаю до новой явной передачи владения.
- `git diff --check` — exit 0. Unit/API/UI не запускались: реализация
  не менялась, подходящих проверок целостности достаточно.
