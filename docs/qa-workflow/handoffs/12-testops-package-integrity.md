# Передача результата: строгая проверка и безопасная сборка TestOps-пакета

Агент: `12`. Дата: 2026-11-14. Статус: `ready` (для интеграции
координатором; CLI по поручению не редактировался).

Устранён обход проверки результатов между `plan` и `package` из
координационной проверки wave-6 (п.3): разбор результатов стал строгим,
сборка пакета сверяет вход с digest плана и согласованным mapping,
проверяет attachments и атомарно публикует результат. Параллельный агент
13 правит состояния upload/verify; его файлы не трогались.

## Изменения

- `infrastructure/reporting/testops/results.py` — единственный изменённый
  модуль реализации. Сохранены публичные имена `load_results`,
  `map_scenarios`, `results_digest`, `scenario_full_name`,
  `rewrite_result`, `build_package`; поведение `load_results` и
  `build_package` ужесточено (см. ниже).
- `tests/unit/test_testops_package_integrity.py` — новый, 26 тестов.
- `test_data/consts/testops_package_integrity.py` — новый, фиктивные
  фиксированные входы и golden-digest детерминированной сборки.

Не менялись: `tools/testops.py`, `state.py`, `client.py`, существующие
unit-тесты, общие документы, api-contract-v1, исторические evidence и
`artifacts/testops` состояния. Сети, TestOps, Docker, Gradle, API/UI не
использовались; токен не читался.

## Публичные интерфейсы (новое и изменённое)

- `ResultsIntegrityError(Exception)` — единый тип ошибок проверки;
  сообщения содержат только имена файлов/uuid, без payload и секретов.
- `load_results(results_dir)` — **теперь строгий**: битый/не-объект JSON,
  отсутствующий строковый `uuid`, дубль `uuid` → `ResultsIntegrityError`
  со списком всех проблем, а не молчаливый пропуск. Возврат прежний.
- `scan_assignments(results_dir, index) -> {uuid: scenario_id}` — строгое
  соответствие 1:1; неизвестный результат и сценарий, сматчивший два
  результата, блокируют.
- `map_scenarios(results, index)` — контракт прежний (нужен `cmd_plan`
  для отчёта `unmapped`); uuid теперь гарантирован сканером.
- `validate_attachments(results_dir, scanned_results)` — все ссылки
  `attachments[].source` (верхний уровень результата, вложенные `steps`,
  `befores`/`afters` и их `steps` в `*-container.json`) должны быть
  строками, оставаться внутри каталога (`resolve()` + `is_relative_to`)
  и существовать. Битый/не-объект container тоже блокируется.
- `assignments_digest(assignments)` — детерминированная идентичность
  mapping `uuid -> (scenario_id, case_id)`; смена bindings меняет digest.
- `build_package_verified(results_dir, destination, *, expected_digest,
  assignments, index=None) -> {"files","results","sha256","input_sha256",
  "assignments_sha256"}` — явный строгий интерфейс: сверяет текущий input
  digest с `expected_digest` плана, требует покрытия assignments ровно
  всех результатов (при `index` — согласованности со свежим mapping),
  проверяет attachments, собирает во временный каталог в
  `destination.parent`, пересчитывает input digest после копирования
  (изменение во время сборки — ошибка) и лишь затем заменяет destination.
  При ошибке destination не создаётся; старый пакет остаётся нетронутым
  результатом прежней успешной сборки (его sha в state по-прежнему
  соответствует содержимому). Исходники не изменяются никогда.
- `build_package(results_dir, destination, assignments)` — сигнатура
  прежняя; внутри тот же строгий путь без привязки к digest/index.
  Уже закрывает «неизвестный/битый результат мимо mapping»: непокрытый
  assignment'ами или битый файл блокирует сборку.
- `verify_package(package_dir, expected_sha256)` и
  `verify_source_digest(results_dir, expected_digest)` — проверки
  актуальности перед upload (см. интеграцию ниже).

## Offline-контрпримеры → regression-тесты (26, все passed)

Класс `TestStrictScan`: битый JSON (имя файла в ошибке), не-объект JSON,
отсутствующий uuid (результат не теряется — файл назван в ошибке), дубль
uuid, неизвестный результат, два результата на один сценарий.

Класс `TestPackageIntegrity`: добавленный после plan результат блокируется
дважды — по устаревшему digest плана и, при пересчитанном digest, по
отсутствию assignment; изменённый исходник; неполные и лишние
assignments; assignment на чужой сценарий; отсутствующий attachment
(верхний step, вложенный step, fixture из container); ссылки `../x` и
абсолютный путь; битый container; изменение источника во время сборки
(monkeypatch повторного digest); ошибка сборки без частичного пакета —
старый пакет цел, новый каталог не создан, `.<name>.tmp-*` не остаются.

Классы `TestPackageIdentity`/`TestPackageVerification`: два прогона сборки
одного входа дают одинаковые `input_sha256`/`assignments_sha256`/`sha256`
и совпадают с golden-константами (`EXPECTED_*` в consts); смена
isolate→bind меняет оба digest; исходники побайтово неизменны;
`verify_package`/`verify_source_digest` принимают целый пакет и блокируют
изменённые.

Класс `TestRecordedEvidence`: реальные `run-5tsmzg1d` (6 результатов) и
`run-vzsatlfk` (4) проходят `scan_assignments` + `validate_attachments`
как read-only вход; каталоги не изменялись.

## Команды и exit codes

| Команда | Exit | Итог |
| --- | --- | --- |
| `sh tools/run-tests.sh one 'tests/unit/test_testops_package_integrity.py::TestStrictScan'` | 0 | 6 passed → `artifacts/harness/run-v8xq1waw/` |
| `… ::TestPackageIntegrity` | 0 | 13 passed → `run-7n9or3cb` |
| `… ::TestPackageIdentity` | 0 | 3 passed → `run-pfqts_dk` |
| `… ::TestPackageVerification` | 0 | 2 passed → `run-z5jayp14` |
| `… ::TestRecordedEvidence` | 0 | 2 passed → `run-ik2wnble` |
| `… tests/unit/test_testops.py::TestScenarioPlan` и 3 других класса | 0 | 4+2+5+3 passed (`run-iary9z25`, `run-nzoud9f9`, `run-0mis7sj0`, `run-0lvrhvk6`) — регрессий нет |
| `sh tools/compile-tests.sh` | 0 | 134 collected (108 + 26) |
| `sh tools/git.sh check` | 0 | чисто |

## Требуемая интеграция CLI/state (точные правки, файлы вне моей области)

1. `cmd_plan` — обернуть скан, иначе traceback вместо 69:
   ```python
   try:
       loaded = results.load_results(results_dir)
   except results.ResultsIntegrityError as error:
       print(f"BLOCKED: {error}", file=sys.stderr)
       return EXIT_BLOCKED
   ```
2. `cmd_package` — перейти на строгий вызов и ловить ошибку:
   ```python
   try:
       info = results.build_package_verified(
           source_dir, destination,
           expected_digest=(state.get("results") or {}).get("sha256"),
           assignments=assignments, index=_scenario_index())
   except results.ResultsIntegrityError as error:
       print(f"BLOCKED: {error}", file=sys.stderr)
       return EXIT_BLOCKED
   ```
   `expected_digest=None` допустим интерфейсом, но CLI обязан передавать
   digest плана — иначе проверка свежести теряется.
3. `state.record_package` — дополнительно сохранить
   `info["input_sha256"]` и `info["assignments_sha256"]` в `state["package"]`
   (согласовать с агентом 13 / schema).
4. `cmd_upload` перед `launch create` — проверка актуальности:
   ```python
   try:
       results.verify_package(package_dir, package["sha256"])
       results.verify_source_digest(source_dir, package["input_sha256"])
   except results.ResultsIntegrityError as error:
       print(f"BLOCKED: {error}", file=sys.stderr)
       return EXIT_BLOCKED
   ```
   При смене `--mode`/bindings между сборками сравнивать и
   `assignments_sha256` записанный в state.

## Предложения по документам (применяет координатор)

- `knowledge/components/infrastructure.md` — добавить запись:
  `build_package_verified`/`verify_package`/`verify_source_digest`/
  `ResultsIntegrityError` из `infrastructure.reporting.testops.results`
  (строгая сборка и проверка пакета загрузки).
- `knowledge/components/consts.md` — запись о
  `test_data.consts.testops_package_integrity` (фиктивные входы и
  golden-digest).
- `knowledge/integrations/testops.md` — в офлайн-потоке описать gate:
  `package` сверяет вход с digest плана и mapping, проверяет attachments,
  собирает атомарно; ошибки разбора → 69 после п.1–2 выше.

## Ограничения

- CLI не изменён: без п.1–2 строгие ошибки в `plan`/`package` придут
  traceback (exit 1), а не 69; digest плана в `cmd_package` пока не
  передаётся — старый вызов `build_package` уже блокирует
  неизвестный/битый/непокрытый результат, но не сверяет свежесть с plan.
- Digest — по содержимому файлов (имя+sha256), не по mtime; каталоги и
  битые симлинки-диры не входят. Attachment-симлинк, ведущий вне
  каталога, блокируется через `resolve()`.
- Проверка attachments покрывает result/container-структуры; битый
  `*-attachment.json` как данные не разбирается (копируется как есть).
- Проверено только офлайн: unit-тесты + read-only скан записанных
  evidence. Живой TestOps, upload и серверная обработка вне области.
