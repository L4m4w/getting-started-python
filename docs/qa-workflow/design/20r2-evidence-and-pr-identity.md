# Точная идентичность evidence/PR и checkpoints TestOps (20R2)

Дата: 2026-11-15. Статус: реализовано и проверено строго offline (временные
каталоги, подменные runner/transports/Git-деревья и read-only проверка
сохранённых артефактов пилота). Live API/UI/SUT, Docker/Gradle, сеть, CI,
внешние записи TestOps и Git commit/push/PR не выполнялись.

Основание:
- [поручение 20R2](../agent-tasks/20r2-evidence-and-pr-identity.md);
- [решение координатора wave 21](../handoffs/coordination-wave-21.md);
- база реализации: [20](20-orchestrator-implementation.md) и
  [20R](20r-orchestrator-corrections.md).

Схема workflow state остаётся совместимой (`workflow_schema_version: 1`);
новые строгие контракты вынесены в `infrastructure/workflow/contracts.py`
и подключены к `Orchestrator`, `GitReadAdapter`, `state.publications_confirmed`
и `tools/workflow.py`. Исправления F1, F4 и F5 сохранены без ослабления.

---

## 1. R1 — полный versioned source и scenario contract

### Проблема в 20R
1. `_source_identity_problems` проверял только файлы, перечисленные в самом
   manifest, не требуя обязательного versioned allowlist `api-contract-v1`,
   уникальности путей и завершённого `rechecked_at`: manifest с одним
   посторонним файлом проходил проверку.
2. `_composition_problems` искал подстроку scenario ID в `name` без проверки
   1:1 биекции, полноты набора, отсутствия дублей, наличия raw Allure JSON,
   совпадения статусов JUnit↔Allure и привязок `ALLURE_ID`. Одновременно на
   настоящем принятом `run-ni_5bvnc` валидатор ложно отклонял все 6 raw
   Allure результатов, так как их русские display titles не содержат
   `CAT-UPD-VAL-*`.

### Реализация
- **`SourceContract` (`infrastructure/workflow/contracts.py`):**
  - требует `source_identity.contract_version == "api-contract-v1"`
    (`tools.harness.API_CONTRACT_VERSION`);
  - вычисляет точное множество обязательных путей
    `set(API_SOURCE_FILES) | set(implementation.payload.test_files)`;
  - проверяет пустые списки `missing == []` и `changed_during_run == []`
    (`null` отклоняется как незавершённый recheck) и непустой `rechecked_at`;
  - проверяет отсутствие дубликатов путей в `files` и `copies`, точное
    совпадение множества путей (любой пропущенный обязательный или
    посторонний путь блокирует gate), sha256 каждого файла против checkout
    (или верифицированной исторической эквивалентности R3) и побайтовое
    совпадение `sources/` без незаписанных файлов.
- **`ScenarioContract` и `validate_scenario_composition`:**
  - боевой контракт по умолчанию `pilot_scenario_contract()` строится из
    `test_data.consts.category_update` (`INVALID_IDS`/`INVALID_NAMES`,
    `VALID_IDS`/`VALID_NAMES`, `TESTOPS_ALLURE_IDS`): `head` ожидает ровно
    6 `passed` (`CAT-UPD-VAL-001..006`), `base` — ровно 4 ожидаемых
    негативных `failed` (`CAT-UPD-VAL-001..004`, без требования 6 passed на
    baseline и без принятия `errors`/`broken`);
  - для JUnit проверяется точное число `<testcase>`, граничный токен
    `(?<![A-Za-z0-9_-])<SID>(?![A-Za-z0-9_-])` (исключает lookalike
    `0010` ↔ `001`), совпадение модуля/функции при параметризации,
    отсутствие пропусков/дублей/чужих кейсов и ожидаемый статус каждого
    сценария;
  - для raw Allure переиспользуются строгие helpers
    `infrastructure.reporting.testops.results`: `load_results` (отклоняет
    битый JSON, пустой или дублирующийся `uuid`), `validate_attachments` и
    `scan_assignments` по `fullName` + `parameters` — без какой-либо опоры
    на display `name`;
  - проверяются равенство статусов JUnit↔Allure, отсутствие дублирующихся
    меток `ALLURE_ID`/`as_id`, совпадение `ALLURE_ID` со связанным TestOps
    ID (а для `head` при принятых `bindings` — обязательное наличие точной
    метки у каждого результата) и согласованность с `TestOps state.json`,
    если он существует; также `accept bindings` блокирует маппинг,
    противоречащий уже записанному execution текущей ревизии;
  - для синтетических unit-тестов `Project` передаёт явный тестовый
    `unit_scenario_contract()` (3 сценария в `head`, 2 негативных в `base`,
    русские display titles без scenario ID) и создаёт полный 15-файловый
    состав `api-contract-v1` + `test_unit_val.py`, не ослабляя боевой
    валидатор.

---

## 2. R2 — отделение Git commit head от patch и dirty snapshot

### Проблема в 20R
`_pr_head_sha` подставлял 64-hex SHA-256 патча в `spec.head_sha` при
`app_head.kind == "patch"` и базовый `tests_repo.commit` при
`tests_repo.dirty == true`, а `--head-sha` принимал любую hex-строку без
проверки Git-объекта и состава дерева.

### Реализация
- Удалены оба fallback в `_candidate_pr_head`: при `app_head.kind != "commit"`
  кандидат `app` равен `None`; при `tests_repo.dirty == True` кандидат
  `tests` равен `None`. Без проверенного коммита `pr prepare` создаёт только
  локальный черновик (`status = "pending"`, `draft = true`,
  `spec.head_sha = null`), а `pr create` возвращает блокировку `exit = 69`
  до обращения к транспорту.
- В `GitReadAdapter` добавлены read-only методы `object_type`,
  `commit_file_bytes`, `commit_file_sha256`, `commit_blob` и
  `changed_files` (`git cat-file` / `git rev-parse --verify ^{commit}` /
  `git diff --name-only` с `GIT_OPTIONAL_LOCKS=0`).
- Единая проверка `_commit_head_problems` вызывается при `pr prepare` (как
  для кандидата ревизии, так и для `--head-sha`), перед `pr create`, в
  `_verify_pr` и при `reconcile`:
  1. SHA обязан существовать в репозитории как объект типа `"commit"`
     (не `blob`/`tree`/`tag`, не отсутствующий объект и не 64-hex patch
     digest);
  2. для `app`: `head_sha != app_base_sha`, ревизия имеет
     `app_head.kind == "commit"` и совпадающий `git_sha`, все файлы
     `context.sources` и объявленные `files` совпадают в дереве коммита по
     sha256/git_blob, а непустой diff `app_base_sha..head_sha` согласован с
     `files`;
  3. для `tests`: `tests_repo.dirty == False`, `head_sha == tests_repo.commit`,
     все файлы `required_source_paths`, документ требований, документы
     принятых артефактов и `files` совпадают в дереве коммита по sha256.
- На уровне инварианта схемы `state.publications_confirmed` дополнительно
  запрещает переход в `published`, если `app_head.kind != "commit"` или
  `tests_repo.dirty == True` (даже при подделке `state.json` на диске).
- В `tools/workflow.py` исправлен возврат кода выхода `cmd_pr` для
  `pr prepare` (`_exit_of(result)` вместо безусловного `0`).

---

## 3. R3 — проверяемая историческая baseline provenance без обхода проверок

### Проблема в 20R
`--provenance` допускался для `head`, поддерживал булев обход
`source_identity_missing: true` и принимал любой словарь, переписанный
вызывающим из отклонённого manifest.

### Реализация
- Полностью запрещены provenance для `variant != "base"` и ключ
  `source_identity_missing`.
- Введена строгая схема `historical_baseline_acceptance` (`schema_version: 1`):

```json
{
  "schema_version": 1,
  "kind": "historical_baseline_acceptance",
  "pilot_id": "category-update-validation",
  "execution_id": "run-vzsatlfk",
  "variant": "base",
  "app_base_sha": "36674280b6878540a9e88f40aaeedf5dfdd2e6ce",
  "manifest_sha256": "a8454b11881fc95bc3e1753535ca759fbbbc53d362f955395489106c0cc86718",
  "junit_sha256": "bcb47c56ec4a449f13097e7d078e8b97bc7074d139a91326e546d31a3eeb156c",
  "allure_results_sha256": "93129e3bc7a8f35a599708d13c0fa37c1c95b8ef7e5bd0b6563b83af86acbdc5",
  "contract_version": "api-contract-v1",
  "tests_repo": {
    "commit": "c84483bf6647678d4052eb377e04a682cdaddd74",
    "dirty": true
  },
  "review_decisions": [
    {
      "path": "docs/qa-workflow/handoffs/coordination-wave-5.md",
      "sha256": "d48d57cdd81b5b03c74ad26f9ee728e307ac21d20a45aa139675c0a98b076347"
    },
    {
      "path": "docs/qa-workflow/handoffs/coordination-wave-14.md",
      "sha256": "535a8e12ace7bd7e5f28931cbfaac2e602337ffc64290105d0197eb1da2d2dbd"
    }
  ],
  "equivalence_scope": {
    "allowed_changed_files": {
      "test_data/consts/category_update.py": {
        "historical_sha256": "dc8b900d34b7401a2bcd5542968dfc15184d20abb2c274905448aa910f96b902",
        "current_sha256": "c66a9a9f94e6a53286e53105212111217e2113de51f78690790cb664c83d3933",
        "reason": "17A added TESTOPS_ALLURE_IDS constants accepted in coordination-wave-14"
      },
      "tests/api/test_category_update.py": {
        "historical_sha256": "455ee7506897f6c7b69b8f6e5d54d8d3bd5ea1b48e478eb39793c71e50dbbd3c",
        "current_sha256": "ebd9deaa18398c306cac5f9ecacc4c554423477c8e38889fd41847878fa7e359",
        "reason": "17A added runtime ALLURE_ID step accepted in coordination-wave-14"
      }
    }
  }
}
```

- `verify_historical_baseline_acceptance` сверяет переданную запись по
  каноническому digest с принятым реестром координатора
  (`DEFAULT_ACCEPTED_HISTORICAL_BASELINES`; в боевом коде — только принятый
  `run-vzsatlfk`), проверяет наличие и sha256 файлов `review_decisions` на
  диске, точные sha256 `manifest.json`, `junit.xml` и `allure-results`,
  вхождение `allowed_changed_files` в `api-contract-v1`, после чего
  выполняет **все** проверки R1 в полном объёме (требуя, чтобы изменённые
  файлы имели `historical_sha256` в manifest/копиях и `current_sha256` в
  живом checkout, а остальные 13 файлов совпадали напрямую).

---

## 4. R4 — durable checkpoints `prepare-testops` (`plan` / `assign` / `package`)

### Проблема в 20R
Повторный вызов `prepare_testops` заново вызывал все три подкоманды
`plan`, `assign`, `package` вместо реального пропуска подтверждённых границ.

### Реализация
- Перед любым делегированным вызовом `_scan_prepare_expectations` и
  `_evaluate_prepare_boundaries` вычисляют ожидаемые `source_sha256`,
  UUID/статусы сценариев и `assignments_sha256`, после чего независимо
  проверяют три границы по `artifacts/testops/<id>/state.json` и диску:
  1. `plan`: совпадение `results.path`, `results.sha256 == source_sha256`,
     пустой `unmapped`, точное множество сценариев, UUID и статусов;
  2. `assign`: `plan` валиден, `unresolved_ids == []`, все `testops_id`
     равны принятым `bindings`;
  3. `package`: `assign` валиден, `mode == "bind"`, совпадают
     `input_sha256`, `assignments_sha256`, а каталог пакета проходит
     `verify_source_digest`, `verify_package`, `load_results` и
     `validate_attachments`.
- На записи execution в `workflow/state.json` сохраняется durable-чекпоинт:

```json
{
  "execution_id": "run-unithead1",
  "source_sha256": "<64hex>",
  "assignments_sha256": "<64hex>",
  "plan": "completed",
  "assign": "completed",
  "package": "completed",
  "package_sha256": "<64hex>",
  "testops_state_sha256": "<64hex>",
  "updated_at": "2026-11-15T19:00:00+00:00"
}
```

- Если все три границы уже валидны:
  - при наличии актуального чекпоинта возвращается `no-op` с **0** вызовов
    subprocess;
  - если `workflow/state.json` не успел сохраниться после успешного
    subprocess (`package`), чекпоинт восстанавливается чтением и проверкой
    `state.json` + пакета (`recovered: true`, **0** вызовов subprocess,
    без пересборки `package`).
- При частичном завершении выполняются только недостающие/инвалидированные
  шаги, с сохранением `workflow/state.json` после каждого подтверждённого
  шага.
- Любой execution с `upload.status != "pending"`, `upload.attempts > 0`
  или непустым `launch` строго неизменяем (блокируется до любых вызовов).
  `publish_testops` дополнительно проверяет целостность пакета перед
  отправкой. Порядок блокировок (`IndexLock` → `WorkflowLock` →
  делегированный `ExecutionLock`) не изменён.

---

## 5. Объяснение обновлённых тестовых ожиданий и фикстур

1. `test_workflow_20r.py::TestF3ExactPrContent::test_spec_records_head_sha`:
   прежний тест прямо закреплял нарушающий контракт fallback
   `spec["head_sha"] == C.APP_PATCH_SHA256` на `app_head.kind == "patch"`.
   Теперь он проверяет оба контракта R2: на `patch` spec остаётся
   черновиком (`head_sha is None`), а на `commit`-ревизии с проверенным
   деревом коммита записывается `C.APP_HEAD_COMMIT_SHA`.
2. PR-тесты доставки/верификации (`TestF1UnresolvedExternalEffect`,
   остальные методы `TestF3ExactPrContent`, `TestPrModel`,
   `test_workflow_orchestrator.py::_drive_to_published`) переведены на
   отдельную фикстуру `project.drive_commit_to_executed()`, в которой
   `FakeGit` хранит независимое замороженное дерево коммита
   `C.APP_HEAD_COMMIT_SHA` и чистое дерево `C.TESTS_COMMIT`. Сама логика
   проверок F1/F3/M4/M10/M11/M18 полностью сохранена.
3. В `test_data/consts/workflow.py` и `test_data/utils/workflow.py`:
   - базовый негативный набор `BASE_SCENARIO_IDS = ["UNIT-VAL-001",
     "UNIT-VAL-002"]` (`BASE_JUNIT` = 2 failed из 3 сценариев проекта)
     устранил прежний искусственный повтор `UNIT-VAL-001#3` при 4 кейсах на
     3 сценария;
   - `Project` создаёт полный 15-файловый состав `api-contract-v1` +
     `test_unit_val.py`, raw Allure JSON с русскими display titles без
     scenario ID и реальную сборку TestOps-пакета через
     `build_package_verified`;
   - в `test_workflow_intents.py::test_imported_uploaded_readonly` убран
     лишний вызов `write_allure_result` без `uuid`/`fullName`/`parameters`
     и со статусом `passed` поверх уже записанных валидных `failed`
     baseline-результатов.
