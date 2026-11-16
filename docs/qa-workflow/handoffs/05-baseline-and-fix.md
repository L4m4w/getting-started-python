# Передача результата: baseline → fix → повторный прогон

Агент: `05`. Дата: 2026-11-14. Статус: `ready`.

На уровне standalone MockMvc доказан эффект минимального исправления:
четыре невалидных имени на base возвращали 200 и доходили до mock downstream;
после добавления `@Valid` возвращают 400 без вызова обновления. Обе допустимые
границы продолжают проходить. Реальная БД и OAuth этим экспериментом не проверены.

## Входы и изменение

- Приложение: `/Users/zenalark/PycharmProjects/Test-java/niffler-py-st3`;
  base SHA `36674280b6878540a9e88f40aaeedf5dfdd2e6ce`, ветка `main`.
- Прочитаны AGENTS.md тестового проекта, requirement v1, scenarios v2,
  handoffs 00/01/02/04, актуальная инструкция Java evidence и локальный
  skill run-tests. Отдельного AGENTS.md в приложении нет.
- Изменён только production-файл
  `niffler-gateway/src/main/java/guru/qa/niffler/controller/CategoriesController.java`:
  `updateCategory(..., @Valid @RequestBody CategoryJson category)`.
  Импорт `Valid` уже существовал; build-файлы, DTO и тест не менялись.
- Исправленная версия — **base + patch**, отдельного head commit нет.
  Commit/push/PR не выполнялись. Все существующие незакоммиченные изменения сохранены.

Идентичность исходников (sha256; полные копии — в `sources/` каждого прогона):

| Файл | Baseline | Base + patch |
| --- | --- | --- |
| `CategoriesControllerValidationTest.java` | `eea6de8d14f8d5f1b7bb84dd2dd384b1d03e3056daad39dacc9568515604ca50` | тот же |
| `CategoriesController.java` | `8c031efc5fbc004f447d435da4089b90008490224cbe891518c854cabb250378` | `32aec8fbd7a7a4533327a3eabeaccb5ba917ae3c0de338dac621c9025830b8a9` |
| `CategoryJson.java` | `d0e0fb63fd34e6b239d0c25596ba106b712d7326aae1164bc5d7e06e5191d552` | тот же |

Patch: `artifacts/java/run-36tzwapr/source.patch`, sha256
`04eb4c874139610869793f0c72843b1a9cb338832973697cf56e25b7ba87937e`.
Хеши baseline проверены против файлов до правки; хеши теста и DTO совпадают
между прогонами. На baseline dirty-флаг объясняется новым тестом 04;
на исправленной версии — также production patch.

## Команды и evidence

Из корня тестового проекта выполнена одна и та же команда с разной меткой:

```sh
sh tools/run-java-test.sh --repo ../niffler-py-st3 \
  --jdk /opt/homebrew/opt/openjdk@21 --module niffler-gateway \
  --tests guru.qa.niffler.controller.CategoriesControllerValidationTest \
  --label baseline \
  --target niffler-gateway/src/main/java/guru/qa/niffler/controller/CategoriesController.java \
  --target niffler-gateway/src/main/java/guru/qa/niffler/model/CategoryJson.java
```

Повторный прогон: та же команда с `--label head` (метка эксперимента,
не SHA). Harness вызывает `:niffler-gateway:cleanTest :niffler-gateway:test`
с `--tests` и `--no-build-cache --rerun-tasks --no-daemon`.
Оба фактических прогона: Python 3.13.15, JDK 21.0.12.1,
Gradle wrapper 8.6; одновременно выполнялся только один Gradle.

| Запуск | Исполнитель | Exit | Total / passed / failed / errors / skipped | Evidence |
| --- | --- | --- | --- | --- |
| Baseline | координатор, для задачи 05 | 1 | 6 / 2 / 4 / 0 / 0 | `artifacts/java/run-l0qw8660/` |
| Base + patch | агент 05 | 0 | 6 / 6 / 0 / 0 / 0 | `artifacts/java/run-36tzwapr/` |

Оба manifest: `status=completed`, `junit.stale_or_missing=false`,
`cached_execution_detected=false`; 12 actionable tasks, 12 executed.
JUnit каждого запуска:
`junit/TEST-guru.qa.niffler.controller.CategoriesControllerValidationTest.xml`.
Проверены manifest, XML и хеши; результаты не взяты из предыдущего прогона 04.

Предварительная попытка 05 `artifacts/java/run-bj_6azjz/` завершилась exit 1
из-за sandbox-доступа к lock в `~/.gradle`: тестов не выполняла и baseline
не считается. Запрос escalation был отменён прерыванием во время ожидания
approval; затем координатор получил доступ и выполнил фактический baseline
`run-l0qw8660`. Production patch внесён только после проверки этого evidence.

## Исходы шести случаев

| Случай | Вход | Baseline | Base + patch |
| --- | --- | --- | --- |
| CAT-UPD-VAL-001 | `""` | FAIL: 200, вызов downstream | PASS: 400, вызова нет |
| CAT-UPD-VAL-002 | три пробела | FAIL: 200, вызов downstream | PASS: 400, вызова нет |
| CAT-UPD-VAL-003 | `A×1` | FAIL: 200, вызов downstream | PASS: 400, вызова нет |
| CAT-UPD-VAL-004 | `A×51` | FAIL: 200, вызов downstream | PASS: 400, вызова нет |
| CAT-UPD-VAL-005 | `A×2` | PASS: 200, точные поля | PASS: 200, точные поля |
| CAT-UPD-VAL-006 | `A×50` | PASS: 200, точные поля | PASS: 200, точные поля |

В baseline у каждого негативного случая XML содержит два расхождения:
ожидался 400 вместо 200 и `NeverWantedButInvoked`. Компиляция/setup успешны.
После исправления настоящая Bean Validation запускает существующие
`@NotBlank`/`@Size(min=2,max=50)` DTO до тела контроллера. В позитивных
случаях captor проверяет id/name/username/archived и ответ 200.

## Дополнительная проверка и пределы

- `git diff --check` в приложении: exit 0. Diff содержит одну добавленную
  аннотацию. Проверен каталог `niffler-gateway/src/test`: кроме теста 04
  других существующих тестов gateway нет; поэтому head-прогон покрывает
  весь текущий тестовый набор затронутого модуля. Тесты spend не запускались:
  его код и внутренние контракты не менялись.
- Исполнены компиляция gateway и все шесть его случаев; NO-SOURCE относится
  только к отсутствующим test resources, не к test task.
- Standalone использует настоящий validator и тестовый JWT resolver,
  но mock SpendClient. Подтверждены HTTP-валидация и отсутствие вызова
  downstream. R3/R4 как сохранённое состояние, реальный OAuth/JWT,
  межсервисная интеграция, Docker и TestOps не проверены.

## Передача 07

Блокеров по 05 нет. Используй base SHA и приложенный patch как точную
идентичность исправленного состояния; не выдавай его за отдельный head SHA.
Следующая обязательная проверка — реальные PATCH/GET на изолированном
окружении по контракту 03 и тестам 06, с сохранением snapshot и очисткой
собственных данных. Для реального эксперимента до/после требуется отдельное
окружение/сборка base; общий checkout не сбрасывать ради него.
