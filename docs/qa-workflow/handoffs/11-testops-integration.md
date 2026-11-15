# Передача результата: подготовленная интеграция с Allure TestOps

Агент: `11`. Дата: 2026-11-14. Статус: `ready`.

Подготовлен проверяемый способ связать шесть сценариев CAT-UPD-VAL-001–006
с проектом TestOps `https://allure.qa.guru/project/5444`, загрузить
результаты выбранного execution поддерживаемым инструментом (`allurectl`)
с фиксацией launch ID/ссылки и привязок, и повторить обработку без дублей
кейсов и повторной загрузки. Живой доступ, создание кейсов, launches и
upload **не выполнялись**: `ALLURE_TOKEN` в окружении отсутствует, запись
в TestOps оставлена отдельному поручению. Это подготовленная интеграция,
а не опубликованные кейсы или результаты.

## Версии входов и источники

- Тестовый проект: `/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
- Инструмент: `allurectl 2.24.0` (GitHub release `allure-framework/allurectl`,
  asset `allurectl_darwin_arm64`, sha256
  `5928e200ba7e82e7c2b13c4d22d9ec1fd415e932445422b9253acfd5f62c1fba`),
  установлен в `~/.local/bin/allurectl` вне репозитория. `allure` 2.46.1
  (Homebrew) — только генератор отчётов, для TestOps не используется.
- `allure-pytest 2.16.2`, pytest 9.1.1, Python 3.13.15.
- Документация (официальная):
  - `allurereport.org/docs/how-it-works-test-identifiers/` — `fullName` для
    параметризованных тестов не зависит от параметров; `testCaseId` и
    `fullName` используются для сопоставления результатов с кейсами.
  - `docs.qameta.io/use-testops/test-cases/test-keys-and-allure-ids/` —
    `ALLURE_ID` — стабильный идентификатор кейса; привязка по ID требует
    существующего кейса, иначе результат «осиротевает».
  - `help.qameta.io …/101000533490` — связывание по полной сигнатуре с
    набором параметров либо по `ALLURE_ID` (приоритет у `ALLURE_ID`).
  - `docs.qameta.io/reference/aql/` — AQL `name ~= "..."` для поиска кейсов.
  - `docs.qameta.io/reference/ecosystem/allurectl/` + `allurectl --help`
    2.24.0 — `upload` для готовых результатов; `test-case list`,
    `launch create/get` с `-o json`; токен через `ALLURE_TOKEN` env.
- Проверено в исходниках `allure_pytest 2.16.2`: `fullName =
  package.class#originalname` без параметров, `testCaseId = md5(fullName)`,
  `historyId` учитывает параметры; `@allure.id` пишет label `as_id`
  (`ALLURE_ID`/`AS_ID` оба читаются TestOps, `ALLURE_ID` актуален).

## Модель шести кейсов

У шести сценариев — два тестовых `fullName`/`testCaseId`, потому что
параметры (`ids=CAT-UPD-VAL-00X`) в `fullName` не входят, а в result JSON
идентификатор параметра вообще не записывается — только значение
`parameters[].value`. Сырой upload дал бы **два** автоматических кейса —
подтверждено и по модели идентификаторов, и по факту: у 6 result-файлов
`run-5tsmzg1d` ровно 2 `testCaseId`.

Выбранная модель — сценарная сигнатура + `ALLURE_ID`:

- Соответствие `результат → сценарий`: по `fullName` и значению параметра
  `name` (через `ast.literal_eval`) по константам
  `test_data.consts.category_update` — единый источник, вымышленных ID нет.
  Незнакомые результаты → `unmapped`, пакет блокируется.
- `package` строит **копию** `allure-results` в
  `artifacts/testops/<execution>/upload-results/` и переписывает сигнатуру
  каждого результата: `name = "CAT-UPD-VAL-00X: <title>"`,
  `fullName = "<orig>[CAT-UPD-VAL-00X]"`, `testCaseId = md5(fullName)`,
  `historyId = md5(fullName + parameters)`. Шесть уникальных сигнатур
  гарантируют шесть кейсов без случайного слияния. Исходники не трогаются.
- Режим `bind`: дополнительно label `ALLURE_ID` с ID существующего кейса —
  детерминированная привязка к согласованным кейсам (рекомендуется).
- Режим `isolate`: пакет без ID; авторизованная загрузка авто-создаёт ровно
  шесть кейсов (повтор dedup по `testCaseId`), затем `resolve` снимает их ID.
- Поиск кейсов: `allurectl test-case list -o json -q 'name ~= "CAT-UPD-VAL"'`;
  кандидат — имя содержит `CAT-UPD-VAL-00X`. 0 → `unresolved`, 1 → `bound`,
  ≥2 → `ambiguous` без выбора; ручная привязка — `assign SCENARIO=ID`.
- Привязки хранятся в `artifacts/testops/<execution>/state.json` (schema 1):
  identity пакета (sha256), сценарии, launch, upload status. Постоянное
  размещение привязок рядом с `testops-mapping.md` — предложение координатору.

## Проверка run-5tsmzg1d и run-vzsatlfk

- `run-5tsmzg1d` (6 passed): все шесть результатов распознаны, `unmapped`
  пуст; isolate-пакет собран детерминированно (два прогона сборки — один
  sha256 `a6f1cddd…`). Для bind-загрузки нужны шесть реальных ID.
- `run-vzsatlfk` (4 ожидаемых failed): четыре результата распознаны;
  отдельный execution и launch возможны той же командой (bind потребует
  четырёх привязок). Публиковать ли baseline-прогон — решение координатора.
- Позитивные кейсы 005–006 на base не выполнялись — это видно по состоянию
  (`scenarios` содержит только 001–004); инструмент не дополняет вымышленными.
- Офлайн-проверки не являются доказательством серверной обработки: exit 0
  `allurectl` требует подтверждения `verify --online`/UI.

## Повторы и сбои (реализовано в state)

- Повторный `plan` обновляет скан без потери привязок/launch/upload; сущностей
  не создаёт. `package` детерминирован; изменённый после сборки пакет
  блокирует upload до пересборки.
- `uploaded` того же execution — жёсткий блок (69); новый фактический прогон
  имеет новый `run-*` и отдельное состояние.
- `failed` — retry только с `--retry`; `unknown` (timeout/прерывание) —
  блок даже с `--retry`, сначала `verify --online` или ручная проверка
  launch. Launch ID записывается сразу после `launch create`, поэтому
  неопределённый исход разрешим без слепого дублирования.
- `in_progress` в state блокирует повтор до ручного разрешения.
- Сбой TestOps не перезапускает тесты и не меняет evidence прогона.
- Ограничения инструмента: `upload` — batch по готовому каталогу (не watch);
  создание launch до upload нужно для точного launch ID; разбор `-o json`
  защитный, живым запросом не проверен.

## Команды и результаты offline-проверок

| Команда | Exit | Итог |
| --- | --- | --- |
| `sh tools/run-testops.sh plan --results artifacts/harness/run-5tsmzg1d/allure-results` | 0 | 6/6 сценариев, state.json записан |
| `… plan --results artifacts/harness/run-vzsatlfk/allure-results` | 0 | 4/4 сценария |
| `… package --execution run-5tsmzg1d --mode isolate` (×2) | 0 | 40 файлов, 6 результатов, sha256 `a6f1cddd…` одинаков |
| `… package --execution run-5tsmzg1d --mode bind` без ID | 69 | список недостающих привязок |
| `… assign …` + `… package --mode bind` (smoke, сброшено) | 0 | `ALLURE_ID` в копиях, источник неизменён |
| `… resolve --execution run-5tsmzg1d` | 69 | требуется `--online` |
| `… resolve … --online` / `… upload … --execute` | 69 | `ALLURE_TOKEN` не задан — до сети |
| `… upload --execution run-5tsmzg1d` | 69 | требуется `--execute` |
| `… verify --execution run-5tsmzg1d --online` | 69 | launch не записан |
| `sh tools/run-testops.sh` | 2 | argparse |
| `sh tools/run-tests.sh group unit` | 0 | **93 passed**, 0 failed (14 новых) |
| `sh tools/compile-tests.sh` | 0 | 108 collected |
| `git diff --check` | 0 | чисто |

Новые unit-тесты `tests/unit/test_testops.py` (14): mapping шести параметров,
unmapped→блок, идемпотентность plan, конфликты assign, bind/isolate-пакеты,
запрет upload без `--execute`/токена, успешная запись launch+uploaded,
auth-failure→failed+`--retry`, timeout→unknown+блок, verify→uploaded,
resolve уникальные/ambiguous, разбор обёрнутого JSON. Живого TestOps в
тестах нет — subprocess подменён.

Evidence: `artifacts/testops/run-5tsmzg1d/` и `run-vzsatlfk/` (state.json,
upload-results для первого), локально, не в Git.

## Изменённые файлы

- `tools/testops.py`, `tools/run-testops.sh` — CLI: `plan`, `status`,
  `assign`, `resolve`, `package`, `upload`, `verify`.
- `infrastructure/reporting/testops/` — `__init__.py`, `results.py`
  (скан/mapping/пакет), `state.py` (state.json schema 1, переходы),
  `client.py` (вызовы allurectl, токен только env).
- `tests/unit/test_testops.py`, `test_data/consts/testops.py`.
- `knowledge/integrations/testops.md` — runbook.
- `knowledge/components/infrastructure.md`, `knowledge/components/consts.md` —
  записи каталога.
- `artifacts/testops/` — локальные состояния планов (gitignored).

Не менялись: `tools/harness.py`, api-contract-v1 файлы, `testops-mapping.md`,
общие README/AGENTS/планы, исторические evidence. Продуктовый код и
checkout приложения не трогались; Docker/Gradle/API не запускались.

## Готово / не проверено

Готово: локальный инструментарий, модель шести кейсов, offline-состояние с
идемпотентностью, runbook, покрытие ошибок unit-тестами, проверка пригодности
`run-5tsmzg1d` (6/6) и `run-vzsatlfk` (4/4) для будущей загрузки.

Не проверено: живой доступ к проекту 5444 (нет `ALLURE_TOKEN`), реальный
формат `-o json` у `test-case list`/`launch create`/`launch get`
(разбор защитный), фактическая привязка `ALLURE_ID` и авто-создание кейсов,
upload-производительность и серверная обработка пакета.

## Предложения координатору (не применены)

1. **Patch proposal разметки API-тестов** (для будущего прогона, чтобы
   сырые результаты уже несли `ALLURE_ID` без перепаковки):
   - `test_data/consts/category_update.py`:
     `TESTOPS_ALLURE_IDS = {"CAT-UPD-VAL-001": <id>, …}` после разрешения ID.
   - `tests/api/conftest.py`, autouse-фикстура:
     ```python
     @pytest.fixture(autouse=True)
     def testops_case_id(request):
         spec = getattr(request.node, "callspec", None)
         case_id = TESTOPS_ALLURE_IDS.get(getattr(spec, "id", ""), None)
         if case_id:
             allure.dynamic.label("ALLURE_ID", str(case_id))
     ```
   Опционально `allure.dynamic.title(f"{spec.id}: …")` для читаемости launch.
   Обновить `api-contract-v1` при принятии.
2. Строка в `knowledge/integrations/ci-github.md` «Allure TestOps и allurectl
   этим harness не подключаются» устарела — заменить ссылкой на testops.md.
3. Постоянное место привязок: `docs/qa-workflow/pilots/category-update-validation/testops-bindings.json` или колонка `testops-mapping.md`.

## Следующее поручение исполнителю внешней синхронизации

Требуются: `ALLURE_TOKEN` в env, разрешение на чтение и отдельно на запись
в проект 5444. Все команды из корня `getting-started-python`:

1. `sh tools/run-testops.sh resolve --execution run-5tsmzg1d --online` —
   read-only; ожидаются 0 совпадений (кейсов ещё нет) или найденные ранее.
2. Создать шесть кейсов `CAT-UPD-VAL-001:…`–`CAT-UPD-VAL-006:…`
   (название/шаги — scenarios.md; эпик «Категории», feature «Переименование
   категории», severity critical) — в UI, либо через `package --mode isolate`
   + `upload` (авто-создание), затем повторный `resolve` для снятия ID.
3. `sh tools/run-testops.sh assign --execution run-5tsmzg1d CAT-UPD-VAL-00X=<id> …`
   при ручном создании.
4. `sh tools/run-testops.sh package --execution run-5tsmzg1d --mode bind`
5. `sh tools/run-testops.sh upload --execution run-5tsmzg1d --execute`
6. `sh tools/run-testops.sh verify --execution run-5tsmzg1d --online`
7. Записать launch ID/URL из `state.json` в `testops-mapping.md`.
8. Опционально — тот же поток для `run-vzsatlfk` (baseline, 4 кейса) и,
   после принятия patch proposal + нового прогона, для сырых результатов.

Блокеров к подготовленной части нет; внешние шаги ждут токен и разрешение.
