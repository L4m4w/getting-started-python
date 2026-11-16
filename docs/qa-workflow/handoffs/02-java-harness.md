# Передача результата: evidence для Java-эксперимента

Агент: `02` (Java harness). Дата: 2026-11-14.
Статус: `ready` — команда Java-прогона реализована и проверена локально
на уровне harness с подменённым процессом. **Gradle в реальном приложении
не запускался** (это работа агентов 04/05); реальных Java-прогонов
через новую команду выполнено: 0.

## Согласованный интерфейс (подтверждён координатором)

```sh
sh tools/run-java-test.sh \
    --repo ../niffler-py-st3 \
    --jdk /opt/homebrew/opt/openjdk@21 \
    --module niffler-gateway \
    --tests 'guru.qa.niffler.controller.CategoriesControllerValidationTest' \
    --label baseline \
    --target niffler-gateway/src/main/java/guru/qa/niffler/controller/CategoriesController.java \
    --target niffler-gateway/src/main/java/guru/qa/niffler/model/CategoryJson.java
```

- Подтвержденные решения координатора: отдельные `--module` + `--tests`
  (команда собирается из валидируемых частей, без сырого хвоста
  Gradle-аргументов); evidence под `artifacts/java/run-*` (отдельный корень,
  вне `artifacts/harness/`); идентичность исходников через `--target` +
  хеши + ограниченный patch.
- `--repo` — абсолютный путь или относительный от корня тестового проекта;
  должен содержать `gradlew`. `--jdk` — JAVA_HOME, проверяется наличие
  исполняемого `bin/java`. `--label` ∈ {`baseline`, `head`}.
- `--target` повторяемый: относительный путь файла внутри репозитория
  приложения; должен существовать (иначе BLOCKED до запуска).
- `--tests`: FQN, `FQN.method` или паттерн с `*`/`?`. Допустимые символы
  `[A-Za-z0-9_.$*?]`, `--module` — `[A-Za-z0-9_-]`; остальное отклоняет
  argparse (exit 2).
- Реально выполняемая команда (записывается в манифест):
  `sh gradlew :<module>:cleanTest :<module>:test --tests '<selector>'`
  с `JAVA_HOME=<jdk>`, cwd = корень приложения. `cleanTest` встроен по
  результатам handoff 01: повторный запуск не может уйти в UP-TO-DATE,
  каждый прогон — реальная попытка выполнения.

## Изменённые файлы

Новые (других файлов не изменено; общие README/AGENTS/каталоги не трогал):

| Файл | Назначение |
| --- | --- |
| `tools/java_evidence.py` | CLI и сбор evidence (внутренняя реализация, как `tools/harness.py`) |
| `tools/run-java-test.sh` | Точка входа через общий `tools/_python.sh` |
| `tests/unit/test_java_evidence.py` | 10 unit-тестов с подменой процесса/git/Java |
| `test_data/consts/java_evidence.py` | Фиксированные входы и ожидания тестов |
| `docs/qa-workflow/handoffs/02-java-harness.md` | Этот отчёт |

## Контракт манифеста `artifacts/java/run-*/manifest.json`

`schema_version: 1`, `kind: "java-gradle-test"` (отличается от Python-прогонов).
Поля:

- `run_id`, `label`, UTC `started_at`/`finished_at`, `status`
  (`running` → `completed` | `launch_error` | `interrupted`), `harness_python`.
- `java`: `home` + первая строка `java -version` выбранного JDK.
- `application`: `path`, `commit`, `dirty` (`null` при сбое git),
  `gradle_wrapper_version` из `gradle-wrapper.properties`.
- `selection`: `module`, `task`, `tests`; `command` — точный argv;
  `environment_overrides` — только `JAVA_HOME` (env не сохраняется).
- `source_identity`: `test_file` (авторазрешение selector →
  `<module>/src/test/java/**.java`, префиксы FQN для `FQN.method`;
  `null` для паттернов и отсутствующих файлов), `files` — список
  `{path, sha256, git_blob, tracked}` для теста и всех `--target`,
  `copies` — файлы, скопированные в `sources/` с сохранением путей,
  `patch` — `source.patch` с `git diff HEAD -- <эти же пути>` или `null`.
- `exit_code` — исходный код Gradle (ненулевой baseline сохраняется как есть).
- `junit`: `files` — скопированные свежие `TEST-*.xml` в `junit/`,
  `stale_or_missing`, `summary` `{total,passed,failed,errors,skipped}`
  по свежим файлам или `null`.
- `cached_execution_detected`: best-effort поиск `> Task :<module>:test`
  с `UP-TO-DATE`/`FROM-CACHE` в `gradle.log`; `null` если лог недоступен.
- `artifacts`: `gradle_log`, `junit`, `sources`, `patch`.

## Семантика свежести JUnit (важно для 04/05)

- До запуска снимается snapshot SHA-256 всех `TEST-*.xml` в
  `<module>/build/test-results/test/`; после — копируются только новые
  или изменённые файлы. Старый XML другого прогона в сводку не попадает.
- `exit 0` при отсутствии свежих XML (`NO-SOURCE` до создания теста,
  кеш) НЕ считается выполненным прогоном: `junit.files: []`,
  `stale_or_missing: true`, `summary: null`. Агенту 05: фактический
  прогон = `files` непустой + `summary` заполнена, а не только exit 0.
- Selector, не совпавший ни с одним тестом, → exit 1 «No tests found»
  и `stale_or_missing: true` — различимо от `launch_error` по `status`.
- Свежий, но нечитаемый XML копируется, `summary: null` — сбой парсинга
  не превращается в успех.

## Коды завершения `tools/run-java-test.sh`

`2` — ошибка аргументов/selector'а; `69` — BLOCKED предварительной
проверки (нет repo/gradlew/`bin/java`, `--target` вне репозитория или
несуществующий; evidence-каталог не создаётся); `127` — `launch_error`;
`130` — `interrupted`; иначе — код завершения Gradle, включая ненулевой
baseline. `69`/`127`/`130` оставляют завершённый манифест (кроме `69`,
которая до создания evidence), как у Python harness.

## Проверки и результаты

Все прогоны — локальные, без сети, Java, Gradle и приложения
(подмены `command`, `_git`, `java_version`, `wrapper_version`,
`_repository_state`).

| Проверка | Результат |
| --- | --- |
| `pytest tests/unit/test_java_evidence.py` | 10 passed, exit 0 |
| `sh tools/compile-tests.sh` | компиляция + collection 52 теста, exit 0 |
| `sh tools/run-tests.sh group unit` | 43 passed / 0 failed, exit 0; evidence `artifacts/harness/run-uiaxknya/` |
| `sh tools/run-java-test.sh` (без аргументов) | usage + exit 2 |
| `--repo /nonexistent --target 'foo/../bar.java'` | BLOCKED×2, exit 69, evidence не создан |
| `sh tools/git.sh check` | exit 0 |

Покрыто тестами: ненулевой baseline + свежий JUnit + идентичность
исходников (sha256/blob/tracked/patch/копии, без утечки содержимого
в манифест); stale XML + UP-TO-DATE лог; свежий нечитаемый XML;
OSError→127 и KeyboardInterrupt→130 с завершённым манифестом; изоляция
двух прогонов (второй не наследует XML первого); отказ argparse на
небезопасные module/selector; разрешение `FQN`/`FQN.method`/паттерна;
BLOCKED без создания evidence.

## Подтверждено / не проверялось

Подтверждено: интерфейс и валидация входов, изоляция и формат evidence,
сохранение exit-кодов и идентичности исходников, семантика свежести
JUnit — всё на подменах.

Не проверялось: реальный Gradle-прогон (по заданию — 04/05); реальный
`git` в приложении (подменён, код аналогичен проверенному harness);
точность `cached_execution_detected` на настоящем выводе Gradle 8.6
(best-effort, маркер по строке `> Task`); `resolve_test_file` покрывает
только `src/test/java` (нет Kotlin/нестандартных sourceSet); модуль
только верхнего уровня (вложенные `:a:b` не поддержаны — для пилота
не требуется); `git diff HEAD` не включает untracked-файлы — их
идентичность закрывают `sha256` + копия в `sources/`.

## Предложения для каталога компонентов (интегрирует координатор)

`knowledge/components/infrastructure.md`, таблица «Локальные
CLI-инструменты harness»:

| Компонент | Путь / вызов | Назначение | Пример |
| --- | --- | --- | --- |
| Java evidence | `tools/run-java-test.sh` → `tools/java_evidence.py` | Один Gradle `--tests` прогон в репозитории приложения: `cleanTest`+`test`, manifest, свежий JUnit, идентичность исходников, `artifacts/java/run-*` | `sh tools/run-java-test.sh --repo ../niffler-py-st3 --jdk /opt/homebrew/opt/openjdk@21 --module niffler-gateway --tests 'FQN' --label baseline` |

`knowledge/components/consts.md`: модуль `test_data.consts.java_evidence` —
фиксированные входы/ожидания unit-тестов Java evidence (селекторы,
relpath'и, JUnit XML, коды выхода).

`knowledge/testing/run-tests.md` (раздел «Результаты и коды завершения»):
абзац про `artifacts/java/run-*` и контракт манифеста `java-gradle-test`
— текст по образцу этого отчёта; координатор решает объём.

## Решения и следующий исполнитель

- Агент 04: кладёт тест в
  `niffler-gateway/src/test/java/guru/qa/niffler/controller/
  CategoriesControllerValidationTest.java`; selector выше разрешается
  в этот файл автоматически — `--target` для него не нужен.
- Агент 05: baseline — команда из шапки с `--label baseline`
  (ожидаемый ненулевой код сохраняется); head — та же команда с
  `--label head` после правки 05. Один Gradle-запуск в checkout
  одновременно (правило координации сохраняется — harness его не
  serializes). Рекомендуемые `--target` для пилота:
  `CategoriesController.java`, `CategoryJson.java`.
- Открыто для координатора: при появлении тестов в нестандартном
  sourceSet или необходимости Kotlin-селекторов расширить
  `resolve_test_file`; при включении build cache в приложении
  (`org.gradle.caching=true`) `cleanTest` не защищает от FROM-CACHE —
  тогда добавить флаг `--rerun` или отключение кеша.
