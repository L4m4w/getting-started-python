# 20R2 — handoff: точная идентичность evidence/PR и checkpoints TestOps

Дата: 2026-11-15. Исполнитель: `20R2`. **Статус: `ready`** — замечания R1–R4
из [wave 21](coordination-wave-21.md) закрыты, исправления F1/F4/F5 сохранены,
добавлены адресные offline regression tests (`tests/unit/test_workflow_20r2.py`,
56 кейсов). Все проверки выполнены **строго offline** (temp dirs, подменные
runner/transports/Git-деревья и read-only проверка сохранённых артефактов
пилота). Live API/UI/SUT, Docker/Gradle, сеть, CI, внешние записи TestOps,
commit/push/PR и запуск других агентов не выполнялись.

Этап 20 и полный MVP принятыми **не объявляются** — решение о приёмке принимает
координатор; независимая задача 21 не начиналась.

---

## 1. Входы, версии и защищённое состояние

- Среда (`sh tools/versions.sh`, exit 0): Python `3.13.15`
  (`.venv/bin/python`), `selenium==4.51.0`, `pytest==9.1.1`,
  `allure-pytest==2.16.2`, `python-dotenv==1.2.1`, `psycopg==3.2.13`,
  `psycopg-binary==3.2.13`.
- Прочитанные входы (SHA-256 на входе/выходе неизменны):
  - `AGENTS.md` — `d4870032…` (рабочий checkout);
  - поручение [20R2](../agent-tasks/20r2-evidence-and-pr-identity.md);
  - решение координатора [coordination-wave-21.md](coordination-wave-21.md);
  - задания [20](../agent-tasks/20-orchestrator-implementation.md) и
    [20R](../agent-tasks/20r-orchestrator-corrections.md),
    [wave 19](coordination-wave-19.md), [wave 20](coordination-wave-20.md),
    [handoff 20R](20r-orchestrator-corrections.md) (`9216c441…`),
    [дизайн 20R](../design/20r-orchestrator-corrections.md) (`b1d72156…`),
    [wave 5](coordination-wave-5.md) (`d48d57cd…`),
    [wave 14](coordination-wave-14.md) (`535a8e12…`).
- Приложение `/Users/zenalark/PycharmProjects/Test-java/niffler-py-st3`
  (read-only, не изменялось): HEAD `36674280b6878540a9e88f40aaeedf5dfdd2e6ce`,
  `git diff` SHA-256
  `04eb4c874139610869793f0c72843b1a9cb338832973697cf56e25b7ba87937e`.
- Защищённые артефакты (19/19 SHA-256 до/после побайтово идентичны,
  см. `protected-sha-{before,after}.txt`):
  - `artifacts/workflow/index.json`: `5df16be1b2d7f1dec17804169bcce8187e6a210c424e5ace91b9223c58725518`;
  - `artifacts/workflow/wf-17431cddc9919d3d/state.json`: `f3182f4299cdf9c7e4fbe11e8efe4d0fe3a04911d71be320891bbe680bb3b436`;
  - `artifacts/testops/run-ni_5bvnc/state.json`: `7bec44e152e68303d85834e3771a125b7639e8c878b391edf9ce54cbde84a13a`;
  - `artifacts/testops/run-ni_5bvnc/upload.log`: `0f40d658d5e805e301bd3a7d41e44cf724672c076023967b5e017a2a586135bf`;
  - `artifacts/testops/run-5tsmzg1d/state.json`: `6da4472277dc42aa4e5136b9574d1521c38105f30c3ad1f944fdde2e7cae57e8`;
  - `artifacts/testops/run-5tsmzg1d/upload.log`: `221898892a4b59e595ec16f4e2533404d143599fda904f3f5cd35ad704d0c21a`;
  - `artifacts/testops/run-vzsatlfk/state.json`: `001c99ba2f582f628a7559d9c79145f1d6798cfc921a3cf035fd599a11695bee`;
  - `artifacts/harness/run-ni_5bvnc/{manifest.json,junit.xml}`: `32f1ec89…` / `0d2e10c2…`;
  - `artifacts/harness/run-vzsatlfk/{manifest.json,junit.xml}`: `a8454b11…` / `bcb47c56…`;
  - `artifacts/harness/run-5tsmzg1d/{manifest.json,junit.xml}`: `343f317e…` / `caf40215…`;
  - оригинальные пробы координатора `coordinator-20-review-20261115/*` и
    `coordinator-20r-review-20261115/*` не запускались на месте и не менялись.
- Все 15 рабочих файлов `api-contract-v1` побайтово совпадают с manifest
  `run-ni_5bvnc`.

---

## 2. Изменённые и созданные файлы

- Код оркестратора:
  - `infrastructure/workflow/contracts.py` (новый) — `SourceContract`,
    `ScenarioContract`, `pilot_source_contract`, `pilot_scenario_contract`,
    `validate_source_identity`, `validate_scenario_composition`,
    `DEFAULT_ACCEPTED_HISTORICAL_BASELINES`,
    `validate_historical_provenance_schema`,
    `verify_historical_baseline_acceptance`;
  - `infrastructure/workflow/adapters.py` — read-only проверка Git-объектов и
    дерева коммита в `GitReadAdapter` (`object_type`, `commit_file_bytes`,
    `commit_file_sha256`, `commit_blob`, `changed_files`);
  - `infrastructure/workflow/state.py` — инвариант `publications_confirmed`
    требует `head` execution для TestOps и чистый immutable commit head для
    `pr.app` (`app_head.kind == "commit"`) и `pr.tests`
    (`tests_repo.dirty == False`);
  - `infrastructure/workflow/orchestrator.py` — интеграция R1–R4 с сохранением
    F1/F4/F5;
  - `tools/workflow.py` — код выхода `pr prepare` (`_exit_of(result)` → 69 при
    блокировке) и актуализация справки `--provenance` / `--head-sha`.
- Тесты и фикстуры:
  - `test_data/consts/workflow.py`, `test_data/utils/workflow.py`;
  - `tests/unit/test_workflow_20r2.py` (новый, 56 тестов);
  - адресная актуализация фикстур/ожиданий в `tests/unit/test_workflow_20r.py`,
    `tests/unit/test_workflow_intents.py`,
    `tests/unit/test_workflow_orchestrator.py` (обоснование — раздел 4).
- Документация и evidence:
  - [дизайн 20R2](../design/20r2-evidence-and-pr-identity.md);
  - этот handoff `docs/qa-workflow/handoffs/20r2-evidence-and-pr-identity.md`;
  - каталог и runbook: `knowledge/components/workflow.md`,
    `knowledge/components/consts.md`, `knowledge/integrations/qa-workflow.md`;
  - новый каталог evidence:
    `artifacts/workflow-implementation/20r2-20261115T195559Z/`.

---

## 3. Исправления, регрессии и доказательства по R1–R4

### R1 — полный source и scenario contract
- **Исправление:** `validate_source_identity` требует точную
  `contract_version == "api-contract-v1"`, пустые списки `missing` и
  `changed_during_run`, заполненный `rechecked_at`, уникальность путей и
  точное равенство множества файлов `set(API_SOURCE_FILES) |
  set(implementation.test_files)`, совпадение sha256 с checkout (или
  верифицированной R3-эквивалентностью) и 1:1 копиями в `sources/` без
  посторонних файлов. `validate_scenario_composition` проверяет биекцию JUnit
  (граничный токен ID, без lookalike `0010` ↔ `001`) и raw Allure через
  `testops.results` (`load_results`, `validate_attachments`,
  `scan_assignments` по `fullName` + `parameters` без зависимости от русского
  display title), уникальность UUID, равенство статусов по варианту (`head`:
  6 `passed`, `base`: 4 негативных `failed`, не `errors`/`broken`) и точные
  метки `ALLURE_ID` (включая проверку при `accept bindings`).
- **Регрессии:** `TestR1SourceAndScenarioContract` (19 параметризованных и
  сценарных проверок): неполный source scope, 3 повтора одного сценария,
  пустой Allure, дубликат UUID и дубликат сценария, lookalike JUnit ID,
  расхождение статусов JUnit↔Allure, ложные/отсутствующие/множественные
  `ALLURE_ID`, конфликт `accept bindings` с записанным `head`, `errors`/`broken`
  на baseline и санитизированная проверка боевого контракта CAT-UPD-VAL.
- **Evidence:** копия пробы wave 21 (`incomplete_identity_and_duplicate_cases`
  и `real_raw_allure_rejected` → `violation_reproduced: false`), а также
  `real_pilot_compatibility_probe.py` на настоящем `run-ni_5bvnc` (read-only:
  6/6 сценариев сопоставлены, `head_manifest_problems: []`, деревья
  артефактов побайтово неизменны).

### R2 — отделение Git commit head от patch и dirty snapshot
- **Исправление:** удалены fallback `app_head.sha256 → head_sha` и
  `dirty tests_repo.commit → head_sha`. До появления проверенного Git commit
  `pr prepare` сохраняет только черновик (`status = "pending"`, `draft = true`,
  `spec.head_sha = null`), а `pr create`, `_verify_pr`, `reconcile` и
  `state.publications_confirmed` блокируют создание/подтверждение/публикацию.
  Кандидат ревизии и явный `--head-sha` проходят `_commit_head_problems` через
  read-only `GitReadAdapter`: объект обязан иметь тип `"commit"`, не совпадать
  с `app_base_sha`, соответствовать `app_head.kind == "commit"` /
  `tests_repo.dirty == False`, а его дерево — совпадать со всеми принятыми
  источниками/документами и списком изменённых файлов `base..head`.
- **Регрессии:** `TestR2GitHeadSeparation` (12 проверок): `app kind=patch`
  черновик и блок `pr create`, подмена `spec.head_sha` на patch digest с
  эхо-транспортом, dirty `tests_repo`, `--head-sha` с отсутствующим объектом /
  `blob` / `base` / чужим деревом / на `patch`-ревизии / с несовпадающим
  списком `files`, отказ `load_state` на поддельном `published`, read-only
  проверка реального `GitReadAdapter` на `HEAD` репозитория и CLI код `69`.
- **Evidence:** проба wave 21 `patch_digest_as_pr_commit` →
  `spec_head_sha: null`, `head_sha_is_patch_digest: false`, `exit: 69`,
  `pr_status: "pending"`, `violation_reproduced: false`.

### R3 — историческая provenance не отключает валидацию
- **Исправление:** запрещены любой `--provenance` для `variant != "base"` и
  флаг `source_identity_missing`. Для исторического `base` принимается только
  `schema_version: 1` (`kind = "historical_baseline_acceptance"`), побайтово
  совпадающая по каноническому digest с записью в принятом реестре
  (`DEFAULT_ACCEPTED_HISTORICAL_BASELINES`, где зафиксирован только
  документированный координатором `run-vzsatlfk`), с проверкой файлов решений
  ревью на диске (`coordination-wave-5.md` и `coordination-wave-14.md`),
  точных sha256 `manifest.json` / `junit.xml` / `allure-results` и
  ограниченного `allowed_changed_files` внутри `api-contract-v1` (сверка и
  исторического sha256 в manifest/копиях, и текущего sha256 в checkout),
  без отключения проверок R1.
- **Регрессии:** `TestR3HistoricalProvenance` (13 проверок): запрет любого
  waiver на `head`, отказ без provenance, отказ на самоподписанный payload по
  отклонённому manifest, матрица искажений (`execution_id`, `manifest_sha256`,
  `junit_sha256`, `allure_results_sha256`, отсутствующий/изменённый документ
  ревью, выход за `api-contract-v1`, дрейф текущего checkout, флаг
  `source_identity_missing`) и положительный импорт принятого baseline.
- **Evidence:** проба wave 21 `head_import_unsigned_provenance` → `blocked`
  (`69`), `violation_reproduced: false`; в `real_pilot_compatibility_probe.py`
  реальный `run-vzsatlfk` без provenance блокируется на двух файлах 17A, а с
  принятой записью `DEFAULT_ACCEPTED_HISTORICAL_BASELINES[0]` проходит с
  `problems: []`.

### R4 — durable checkpoints локальной цепочки TestOps
- **Исправление:** `prepare_testops` пересчитывает `source_sha256`,
  UUID/статусы и `assignments_sha256` и независимо верифицирует три границы
  (`plan`, `assign`, `package`) по `artifacts/testops/<id>/state.json` и
  каталогу пакета (`verify_source_digest`, `verify_package`, `load_results`,
  `validate_attachments`), сохраняя durable-чекпоинт `testops_prepare` в
  `workflow/state.json`. Повтор на готовом execution возвращает `no-op` с **0**
  subprocess-вызовов; после сбоя выполняются только незавершённые шаги; при
  потере save `workflow/state.json` после успеха subprocess чекпоинт
  восстанавливается из верифицированного `state.json` без пересборки `package`.
  Любой execution с `upload.status != "pending"`, `attempts > 0` или непустым
  `launch` строго неизменяем. `publish_testops` дополнительно проверяет пакет
  до отправки; `sent → verify-testops` по-прежнему не вызывает `upload`.
- **Регрессии:** `TestR4TestOpsCheckpoints` (12 проверок): повтор готового
  `prepare` (0 вызовов), сбой после `plan` и после `assign`, краш процесса
  сразу после успешного subprocess `plan` / `assign` / `package` до сохранения
  workflow state, инвалидация локального `pending` пакета/результатов и
  неизменяемость `in_progress`/`sent`/`uploaded`/`unknown`/`failed`.
- **Evidence:** проба wave 21 `prepare_replays_completed_steps` →
  `second: {"outcome": "no-op", ...}`, `second_dispatches: []`,
  `violation_reproduced: false`.

---

## 4. Обоснование обновления прежних тестовых ожиданий и фикстур

1. `tests/unit/test_workflow_20r.py::TestF3ExactPrContent::test_spec_records_head_sha`:
   прежнее ожидание `assert spec["head_sha"] == C.APP_PATCH_SHA256` прямо
   закрепляло нарушающий контракт R2 fallback `patch digest → Git commit head`.
   Тест обновлён: проверяет, что на `kind="patch"` `spec["head_sha"] is None`
   (черновик), а на `kind="commit"` записывается проверенный Git commit SHA
   `C.APP_HEAD_COMMIT_SHA`.
2. PR-тесты доставки и верификации (`TestF1UnresolvedExternalEffect`,
   остальные кейсы `TestF3ExactPrContent`, `TestPrModel` в
   `test_workflow_intents.py`, `_drive_to_published` в
   `test_workflow_orchestrator.py`): ранее опирались на `drive_to_executed()`
   с `app_head_kind="patch"`, где PR-вызовы проходили только из-за удалённого
   fallback `patch → head_sha`. Переведены на отдельную фикстуру
   `drive_commit_to_executed()` с замороженным деревом коммита
   `C.APP_HEAD_COMMIT_SHA` и чистым `C.TESTS_COMMIT` — все проверки F1/F3/M4/
   M10/M11/M18 сохранены без ослабления.
3. `test_data/consts/workflow.py` и `test_data/utils/workflow.py`:
   - `BASE_SCENARIO_IDS = ["UNIT-VAL-001", "UNIT-VAL-002"]` (`BASE_JUNIT` = 2
     failed из 3 сценариев) заменил прежний `total=4` на 3 сценариях, который
     порождал дубликат `UNIT-VAL-001#3`;
   - положительные фикстуры `Project` теперь создают полный 15-файловый состав
     `api-contract-v1` + `test_unit_val.py`, raw Allure JSON с русскими
     display titles без scenario ID и реальный пакет через
     `build_package_verified`;
   - в `test_workflow_intents.py::test_imported_uploaded_readonly` удалён
     лишний вызов `write_allure_result` без `uuid`/`fullName`/`parameters` и
     со статусом `passed`, нарушавший строгую целостность R1 на `failed`
     baseline.

---

## 5. Выполненные проверки (локальные, offline)

| Команда / проверка | Область | Exit | Результат |
| --- | --- | --- | --- |
| `sh tools/versions.sh` | Окружение / pins | 0 | Python 3.13.15, все pins совпали |
| `.venv/bin/python -m pytest tests/unit/test_workflow_20r2.py -q` | Новые регрессии 20R2 | 0 | **56 passed** |
| `.venv/bin/python -m pytest tests/unit/test_workflow*.py -q` | Все workflow unit-тесты | 0 | **169 passed** |
| Копия оригинальных 5 проб 20 (`original-five-probes.py`) | F1–F5 | 0 | **5/5** `violation_reproduced: false` |
| Копия новых 5 проб wave 21 (`probe.py`) | R1–R4 | 0 | **5/5** `violation_reproduced: false` |
| `real_pilot_compatibility_probe.py` (read-only) | `run-ni_5bvnc` + `run-vzsatlfk` | 0 | 6/6 head + 4/4 base mapped, 0 мутаций |
| `sh tools/compile-tests.sh` | Компиляция + collection | 0 | **417 collected** (не выполнение UI/API) |
| `sh tools/run-tests.sh group unit` | Полная группа `unit` | 0 | **402 passed**, 0 failed/errors/skipped (`artifacts/harness/run-xjenmsks/`) |
| `sh tools/git.sh check` и `git -C ../niffler-py-st3 diff --check` | Whitespace / diff hygiene | 0 | Чисто в обоих репозиториях |
| Проверка локальных Markdown-ссылок и SHA защищённых файлов | Документы + 19 SHA + 15 API files | 0 | 0 битых ссылок, 19/19 SHA идентичны, утечек секретов нет |

Материалы запуска unit-группы:
- JUnit: `artifacts/harness/run-xjenmsks/junit.xml`
- Allure: `artifacts/harness/run-xjenmsks/allure-results`
- Manifest: `artifacts/harness/run-xjenmsks/manifest.json`

Материалы регрессий и проб 20R2:
`artifacts/workflow-implementation/20r2-20261115T195559Z/`
(`original-five-probes.py`, `original-five-probe-results.json`, `probe.py`,
`probe-results.json`, `real_pilot_compatibility_probe.py`,
`real-pilot-compatibility-results.json`, `protected-sha-before.txt`,
`protected-sha-after.txt`, `commands.md`, `verification-summary.json`).

---

## 6. Ограничения и непроверенное

- Все проверки этого этапа — локальные offline-тесты и read-only аудит ранее
  сохранённых материалов. Реальные API/UI прогоны на стенде, Docker/Gradle,
  сетевые вызовы TestOps (`resolve`/`upload`/`verify --online`), live PR
  transport (`gh`/GitHub API) и Git `commit`/`push`/создание PR **не
  выполнялись**.
- В текущем состоянии репозиториев (`niffler-py-st3` имеет `app_head.kind =
  "patch"` без коммита исправления, `getting-started-python` имеет
  `dirty = true` с незакоммиченными файлами) оркестратор по контракту R2
  допускает только черновые PR-спецификации (`draft = true`, `head_sha = null`)
  и блокирует `pr create` / переход в `published` до создания реальных
  коммитов с верифицируемыми деревьями и появления разрешённого live PR
  транспорта.
- Реестр `DEFAULT_ACCEPTED_HISTORICAL_BASELINES` не является криптографической
  подписью: он обеспечивает детерминированную проверяемую привязку к
  конкретным принятым координатором артефактам и документам ревью на диске
  вместо произвольного булева обхода валидации.
- Общие индексные документы (`docs/qa-workflow/README.md`,
  `docs/qa-workflow/agent-tasks/README.md`, `docs/plans/qa-workflow-mvp.md`)
  не редактировались и оставлены для интеграции координатором.
