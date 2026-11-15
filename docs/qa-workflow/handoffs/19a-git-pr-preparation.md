# 19A — локальный пакет подготовки Git/PR

Дата: 2026-11-15. Исполнитель: `19A`.
Статус: `needs_decision` — пакет собран и проверен локально; состав
публикации содержит открытые решения координатора (см. раздел «Решения»).
Commit/push/PR не выполнялись; index, ветки, checkout и remotes не менялись.

Поручение: [19a-git-pr-preparation.md](../agent-tasks/19a-git-pr-preparation.md).
План волны: [coordination-wave-18.md](coordination-wave-18.md).

## Входы и версии

Прочитаны: AGENTS.md (QA), `docs/plans/qa-workflow-mvp.md`,
coordination-wave-15/17/18, `08-final-review.md`, testops-mapping,
manifest `run-ni_5bvnc`, java-manifest `run-36tzwapr`.
В приложении `niffler-py-st3` AGENTS.md отсутствует (проверено find —
только README.md модулей).

| Репозиторий | HEAD | Ветка | Upstream (локальный ref) |
| --- | --- | --- | --- |
| QA `getting-started-python` | `c84483bf6647678d4052eb377e04a682cdaddd74` | `MVP_workflow` | `origin/MVP_workflow` == HEAD |
| Приложение `niffler-py-st3` | `36674280b6878540a9e88f40aaeedf5dfdd2e6ce` | `main` | `origin/main` == HEAD |

Remotes: QA — `git@github.com:L4m4w/getting-started-python.git`;
приложение — `https://github.com/L4m4w/niffler-py-st3.git`.
Credentials в URL отсутствуют. Локальные remote refs — кеш без fetch;
свежая серверная картина не проверялась (сеть в задаче не использовалась).
Staged-изменений нет в обоих репозиториях.

## Идентичность: HEAD vs dirty snapshot vs immutable head

- **Приложение.** Текущий HEAD `36674280…` — это одновременно принятый
  **base** пилота. Единственное tracked-изменение — `@Valid` в
  `CategoriesController.updateCategory`. Текущий `git diff`
  **байт-идентичен** принятому patch: SHA-256
  `04eb4c874139610869793f0c72843b1a9cb338832973697cf56e25b7ba87937e`
  (сверено с `artifacts/integration/catupdval-rerun/base-to-fix.patch`).
  **Immutable head с пилотным изменением отсутствует**: сборки fix в
  прогонах 05/07/10/17 были `base + patch`, а не Git-коммитом. Dirty
  snapshot digest не заменяет будущий head SHA; после commit появится
  новый immutable head, и старые прогоны остаются прогонами base+patch.
- **QA.** HEAD `c84483b`; весь пилотный код незакоммичен. Manifest
  `run-ni_5bvnc` зафиксировал `repository.commit=c84483b`, `dirty=true`
  и per-file source identity (ниже). Будущий commit даст новый head,
  не меняющий исторический execution.

## Состав изменений

### Инвентаризация

- QA: 18 modified tracked + 100 untracked файлов (`git ls-files --others
  --exclude-standard`; игнорируемые `.env`, `artifacts/`, `__pycache__/`,
  `.idea/`, `.venv/` в перечень не входят — `.gitignore` их покрывает).
- Приложение: 1 modified + 1 untracked файл.

### Приложение — предлагаемый draft PR (1 файл fix + 1 файл regression)

| Файл | Статус | Вердикт | Причина |
| --- | --- | --- | --- |
| `niffler-gateway/src/main/java/guru/qa/niffler/controller/CategoriesController.java` | M | **включить** | Production fix: только `@Valid` перед `@RequestBody updateCategory`; diff == принятому patch `04eb4c87` |
| `niffler-gateway/src/test/java/guru/qa/niffler/controller/CategoriesControllerValidationTest.java` | ?? | **включить** | **Java-регрессия (выделена явно)**: standalone MockMvc, 6 случаев; baseline 4 failed (red на base), head 6/6 (`run-36tzwapr`); sha256 файла `eea6de8d…` == записанному в манифесте head-прогона |

Иных кандидатов в приложении нет: untracked содержит только `src/test/` с
этим единственным файлом; build-каталоги игнорируются `.gitignore`.

### QA — предлагаемый draft PR

**Включить — изменённые tracked (10):**

`requirements.txt` (+psycopg 3.2.13 для fixture cleanup),
`tools/harness.py` (группа `api`, `api-contract-v1` source identity,
env-флаги), `tests/unit/test_harness.py`, `test_data/consts/harness.py`,
`knowledge/components/{README,consts,fixtures,infrastructure}.md`,
`knowledge/integrations/ci-github.md`, `knowledge/testing/run-tests.md`.

**Включить — untracked код/документы (32):**

- `infrastructure/http/{__init__,client,oauth}.py` — API transport + OAuth/PKCE;
- `infrastructure/reporting/testops/{__init__,client,lifecycle,rest,results,state,verification}.py` — TestOps tooling;
- `tests/api/{__init__,conftest,test_category_update}.py` — 6 API-сценариев CAT-UPD-VAL с закреплёнными `ALLURE_ID`;
- `tests/unit/{test_http_client,test_java_evidence,test_testops,test_testops_lifecycle,test_testops_package_integrity,test_testops_rest,test_testops_verification}.py`;
- `test_data/consts/{category_update,java_evidence,testops,testops_lifecycle,testops_package_integrity,testops_rest,testops_verification}.py`;
- `tools/{java_evidence.py,run-java-test.sh,run-testops.sh,testops.py}`;
- `knowledge/integrations/testops.md` — runbook нового tooling.

Причина: единый пилотный изменение — API-тесты + их транспорт, harness
provenance, TestOps-публикация и каталоги компонентов, обязательные по
AGENTS.md при новых общих компонентах.

**Требует решения (70 файлов, `docs/qa-workflow/**`, `docs/plans/`):**

| Группа | Файлы | Склонение |
| --- | --- | --- |
| Пилотные документы | `pilots/category-update-validation/{requirement.md (M), scenarios.md (M), testops-mapping.md (??)}` | склонение **включить** в QA PR — документация покрытия и bindings |
| Процессные материалы | `docs/qa-workflow/handoffs/` (49 ??, включая `evidence/01-build-readiness/*.log`), `agent-tasks/` (3 M + 12 ??), `README.md` (M), `docs/plans/qa-workflow-mvp.md` (M) | склонение **исключить** из product PR либо отдельным commit/PR — внутренний аудит мультиагентного процесса; исторические handoffs не править и не удалять |

`agent-tasks/19a-*.md`, `19b-*.md` и этот handoff — материалы текущей
волны; 19B редактирует параллельно, его файлы не трогал.

**Исключить:** `.env`, `artifacts/`, `__pycache__/`, `.idea/`, `.venv/`,
`.DS_Store`, `allure-results/`, `allure-report/` — gitignored, секреты и
локальные evidence в PR не входят.

## Сопоставление принятых source identities

| Identity | Принятое значение | Текущая проверка 19A |
| --- | --- | --- |
| App patch (dirty diff) | SHA-256 `04eb4c87…` (принято в 10/17B/17C) | `git diff` байт-идентичен — совпал |
| `CategoriesController.java` (fix) | `32aec8fb…` (java-manifest head) | совпал |
| `CategoriesControllerValidationTest.java` | `eea6de8d…` (java-manifest) | совпал |
| 15 файлов `api-contract-v1` | sha256 из manifest `run-ni_5bvnc` (`32f1ec89…`) | все 15 совпали с текущими файлами |
| Manifest `run-ni_5bvnc` | `32f1ec8950…` (wave 15/18A) | пересчитан — совпал |

`missing`/`changed_during_run` в manifest пусты; container/image binding
выполнен и совпал с declared (`f496835f…`). Это измерения прошлых
исполнителей, подтверждённые текущим совпадением хешей, а не новый прогон.

## Evidence-пакет

`artifacts/git-pr/19a-20261115T124815Z/` (gitignored):

- `inventory/` — полный read-only Git-дамп обоих репозиториев
  (HEAD/branch/upstream/status/remotes/refs/log/staged/diff-check) и
  полные списки untracked;
- `app/base-to-fix.patch`, `app/sources/` (2 файла), `app/SHA256SUMS.txt`,
  `app/allowlist-app.txt`;
- `qa/tracked-modifications.patch` (все 18 M-файлов одним diff),
  `qa/sources/` (42 файла: 32 untracked + 10 modified), `qa/SHA256SUMS.txt`,
  `qa/allowlist-qa.txt`, `qa/DECISION-FILES.sha256` (70 файлов
  `docs/qa-workflow`+`docs/plans` — хеши без копий);
- `secret-scan.txt` — 3 срабатывания, все ложные (синтетические
  unit-константы `UNIT_PASSWORD="offline"`, `API_TOKEN="unit-api-token"`,
  HTML-фикстура формы); реальных секретов нет;
- `recheck.txt` — финальная перепроверка status/diff-check и дерево пакета.

Целостность: каждый snapshot-снимок пересчитан против текущего working
tree — все хеши совпали (OK).

## Предлагаемые draft PR

### PR-1: приложение `niffler-py-st3`

- Ветка (предложение): `fix/cat-upd-val-gateway-validation`, base: `main`.
- Title: `fix(gateway): validate request body on PATCH /categories/update`
- Body (черновик):

```markdown
## Проблема
`CategoriesController.updateCategory` принимал `@RequestBody` без
`@Valid`: невалидные имена категорий (пустое, пробелы, <2 и >50 символов)
проходили с HTTP 200 и сохранялись в `niffler-spend`.

## Изменение
- `@Valid` перед `@RequestBody CategoryJson` в `updateCategory`
  (DTO-ограничения уже существуют и не расширялись).
- **Регрессионный тест** `CategoriesControllerValidationTest`
  (standalone MockMvc): 4 невалидных случая ожидают HTTP 400 без вызова
  `SpendClient`; 2 граничных (2 и 50 символов) — HTTP 200 с контрактом
  тела и прокидываемыми полями.

## Проверка (исторические прогоны, не из этого PR)
- Baseline `36674280` без изменения: 4 негативных случая failed
  (`artifacts/java/run-pqzz4gmr`, exit 1) — тест воспроизводит дефект.
- С изменением: 6/6 passed (`artifacts/java/run-36tzwapr`, exit 0).
- Сквозной API-прогон QA-репозитория на сборке base+patch: 6 passed,
  execution `run-ni_5bvnc`; TestOps launch 57317 (см. связанный PR
  автотестов — ссылка будет добавлена после его создания).

## Идентичность
Base SHA: `36674280b6878540a9e88f40aaeedf5dfdd2e6ce`.
До merge этого PR изменение существовало как uncommitted patch
SHA-256 `04eb4c874139610869793f0c72843b1a9cb338832973697cf56e25b7ba87937e`;
исторические evidence ссылаются на base+patch, а не на head SHA ветки.

## Ограничения
- Проверены только случаи CAT-UPD-VAL; unicode/null/trim/чужой владелец
  вне scope. Spend PATCH и его DTO вне scope этого пилота.
```

### PR-2: QA `getting-started-python`

- Ветка (предложение): `feature/cat-upd-val-api-tests`,
  base: **требует решения** — `MVP_workflow` (текущий upstream, == HEAD)
  или `master` (`origin/master` == `9770f36`, отстаёт).
- Title: `test(api): CAT-UPD-VAL — валидация обновления категории (API + evidence/TestOps tooling)`
- Body (черновик):

```markdown
## Покрытие
Шесть параметризованных API-сценариев CAT-UPD-VAL (R1–R4) для
PATCH `/api/categories/update` через gateway: 4 негативных ("" / пробелы /
1 символ / 51 символ) и 2 граничных (2 и 50). Каждый сценарий помечен
runtime `ALLURE_ID`; bindings: 001→55376, 002→55374, 003→55375,
004→55377, 005→55373, 006→55378 (проект 5444).

## Red/green
- base `36674280`: 4 негативных failed, HTTP 200 + имя сохранено
  (execution `run-3zbyks5d` исторический; `run-vzsatlfk` повтор).
- base+patch `04eb4c87`: 6 passed, финальный execution `run-ni_5bvnc`;
  TestOps launch 57317, uploaded/confirmed, attempts=1.
- Позитивные случаи на API base не выполнялись (scope пилота).

## Состав
API-тесты и fixtures (`tests/api/`), HTTP/OAuth транспорт
(`infrastructure/http/`), provenance harness (`tools/harness.py`,
manifest schema 2, `api-contract-v1`), Java evidence runner
(`tools/java_evidence.py`), TestOps CLI
(`tools/testops.py` + `infrastructure/reporting/testops/`),
константы `test_data/consts/`, unit-тесты, каталоги knowledge.
[если включены] пилотные docs: requirement/scenarios/testops-mapping.

## Ограничения evidence
- F-1/F-2 ревью 08: у прогонов 07 нет сохранённого post-down evidence и
  полной per-run привязки источник→образ→контейнер; provenance 10/17 —
  operator-declared + live container check, без независимой rebuild-
  аттестации. См. handoff 08-final-review.
- Успех API/TestOps не закрывает MVP: нет immutable head с изменением,
  оркестратор и сквозная идемпотентность не реализованы.
- Исторические handoffs/evidence — по решению о составе (см. PR-состав).

## Pending
- head SHA ветки появится после commit; внешние ссылки на draft PR
  приложения добавить после его создания.
- TestOps IDs заполнены и подтверждены; mapping — testops-mapping.md.
```

Иной состав не предлагается: один product PR на репозиторий. Разделение
процессных документов в отдельный PR — опция для координатора.

## План будущих Git-операций (не исполнять без разрешения)

```sh
# Приложение (в niffler-py-st3):
git switch -c fix/cat-upd-val-gateway-validation
git add niffler-gateway/src/main/java/guru/qa/niffler/controller/CategoriesController.java \
        niffler-gateway/src/test/java/guru/qa/niffler/controller/CategoriesControllerValidationTest.java
git commit -m "fix(gateway): validate request body on PATCH /categories/update"
git push -u origin fix/cat-upd-val-gateway-validation
gh pr create --draft --base main --title "..." --body "..."

# QA (в getting-started-python), по решению о составе и base:
git switch -c feature/cat-upd-val-api-tests
git add <allowlist-qa.txt: 10 M + 32 ??>
# при включении пилотных docs — добавить их тем же или отдельным commit
git commit -m "test(api): CAT-UPD-VAL category update validation pilot"
git push -u origin feature/cat-upd-val-api-tests
gh pr create --draft --base <MVP_workflow|master> --title "..." --body "..."
```

Проверки непосредственно перед commit (после любых правок оркестратора
или иных изменений рабочего дерева):

1. `git status`/`git diff` — пересобрать инвентаризацию и пакет;
2. пересчитать SHA-256 всех файлов allowlist, сверить с manifest
   `run-ni_5bvnc` и patch `04eb4c87`; при расхождении обновить пакет и
   пометить provenance историческим;
3. `sh tools/compile-tests.sh` и `sh tools/run-tests.sh group unit`
   (код менялся — повторить, не полагаться на 233 passed из wave);
4. `git diff --check` обоих репозиториев; секрет-скан staged-состава;
5. после commit: записать новый head SHA в пакет; будущий head не
   превращает старый execution в прогон этого head — обновить PR body.

Точно неизвестно (зафиксировать при публикации): свежесть `origin/*`
без fetch; write-доступ и владение репозиториями (`L4m4w`); наличие
`gh` CLI; окончательная base-ветка QA PR; судьба процессных документов.

## Собственные проверки 19A

| Команда | Результат |
| --- | --- |
| `git status`/`rev-parse`/`branch -r`/`remote -v` обоих репозиториев | exit 0; инвентаризация в `inventory/` |
| `git diff` приложения vs `catupdval-rerun/base-to-fix.patch` | IDENTICAL, sha256 `04eb4c87…` |
| Сверка sha256 15 api-файлов с manifest `run-ni_5bvnc` | 15/15 совпали |
| Сверка sha256 Java-файлов с java-manifest `run-36tzwapr` | совпали (`eea6de8d`, `32aec8fb`) |
| Integrity snapshots пакета vs working tree | OK, расхождений 0 |
| Секрет-скан пакета | 0 реальных секретов (3 ложных срабатывания) |
| `git diff --check` QA / приложение | exit 0 / exit 0 |
| Финальный recheck status обоих репозиториев | без изменений; `recheck.txt` |

Не выполнялось: сеть/fetch, commit/push/PR, API/UI, Docker/Gradle, CI,
TestOps, unit/collection-прогоны (документационная подготовка), изменение
index/веток/config. Файлы 19B, общие индексы и исторические handoffs не
трогал; все незакоммиченные изменения сохранены.

## Ограничения и решения координатора

1. Состав `docs/qa-workflow/**` (70 файлов): включить в QA PR / отдельный
   docs-PR / оставить внутренними. Склонение указано выше.
2. Base-ветка QA draft PR (`MVP_workflow` vs `master`) и право записи
   в `L4m4w/*` репозитории.
3. Пакет **предварительный**: после реализации оркестратора (задание 20)
   и любых правок кода его нужно актуализировать — повторить инвентаризацию,
   хеши, проверки и PR body.
4. Новый immutable head появится только после разрешённого commit; до
   этого валидная идентичность пилотного изменения — base + patch SHA-256.
5. Draft PR и cross-links между PR — после разрешения публикации; URL
   не существуют и не выдумываются.
