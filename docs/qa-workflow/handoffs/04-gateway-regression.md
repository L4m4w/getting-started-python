# Передача результата: регрессионный MockMvc-тест gateway

Агент: `04` (MockMvc-тест). Дата: 2026-11-14.
Статус: `done` — тест написан, скомпилирован и фактически выполнен на base
через Java evidence harness. Гипотеза о пробеле в валидации PATCH
**воспроизведена на уровне контроллера**: все четыре невалидных имени доходят
до `SpendClient.updateCategory` и возвращают HTTP 200 вместо 400.
Исправление продукта не входило в задачу и не вносилось.

## Входы и версии

- Приложение `niffler-py-st3`: `HEAD = 36674280b6878540a9e88f40aaeedf5dfdd2e6ce`
  (`main`). После работы `git status --porcelain` → только untracked
  `niffler-gateway/src/test/`; production-код не изменён.
- JDK: `/opt/homebrew/opt/openjdk@21` (21.0.12.1), Gradle wrapper 8.6 —
  как зафиксировано в отчёте 01.
- Прочитаны: `AGENTS.md` тестового проекта, requirement/scenarios пилота,
  `api-framework-assessment.md`, handoffs 00/01/02, `coordination-wave-1.md`.
  Отдельного AGENTS.md в репозитории приложения нет.
- Проверено по байткоду spring-webmvc 6.2.5: в дефолтных resolvers
  `RequestMappingHandlerAdapter` нет `AuthenticationPrincipalArgumentResolver`
  (в полном контексте его регистрирует Spring Security, в standalone — нет),
  поэтому custom resolver, переданный в `setCustomArgumentResolvers`,
  обрабатывает `@AuthenticationPrincipal Jwt` до catch-all resolvers.

## Изменённые файлы

В приложении — один новый файл (других правок нет, build-файлы не тронуты,
`spring-security-test` не добавлялся):

- `niffler-gateway/src/test/java/guru/qa/niffler/controller/CategoriesControllerValidationTest.java`
  - sha256: `eea6de8d14f8d5f1b7bb84dd2dd384b1d03e3056daad39dacc9568515604ca50`
  - git blob: `9bedafd0bbbd52ecef682bdae790ea4797019ed0` (файл untracked;
    `source_identity.patch` в манифесте = `null`, идентичность закрыта
    sha256 + копией в `sources/` прогона)

В тестовом проекте — этот отчёт.

## Устройство теста

Standalone MockMvc реального `CategoriesController` без Spring-контекста:

- `MockMvcBuilders.standaloneSetup(new CategoriesController(spendClient))`
  с явным `setValidator(new LocalValidatorFactoryBean())` — настоящая
  Bean Validation из `spring-boot-starter-validation`, не зависящая от
  автодетекта `OptionalValidatorFactoryBean`.
- `SpendClient` — Mockito mock. В негативных тестах стабов нет: на base mock
  вызывается, возвращает `null`, контроллер отдаёт 200 с пустым телом —
  отсутствие валидации не маскируется NPE/500. Стаб `updateCategory`
  объявлен только внутри позитивного теста: при strict-stubs неиспользуемый
  стаб в негативных случаях давал бы `UnnecessaryStubbingException` на head
  и маскировал результат фикса.
- JWT principal — вложенный `TestJwtPrincipalArgumentResolver`
  (`HandlerMethodArgumentResolver`): поддерживает параметры с
  `@AuthenticationPrincipal` типа `Jwt` и возвращает реальный `Jwt`
  с claim `sub = "duck"`. `spring-security-test` не требуется — решение
  координатора соблюдено.
- `GlobalExceptionHandler` не регистрируется (замечание 00): статус 400
  обеспечивает дефолтная обработка `MethodArgumentNotValidException`;
  форма `ErrorJson` не проверяется.
- Негативный тест собирает оба факта в одном `assertAll` (HTTP-статус и
  `verify(never())`), поэтому на base в одном прогоне видны оба расхождения,
  а не только первое.
- Позитивный тест: `archived=true` в запросе (проверка сохранности флага
  значимее, чем false→false), ответ проверен по `jsonPath`
  (вторичная contract-проверка M-2), переданные downstream данные —
  `ArgumentCaptor` по всем четырём полям, включая `username` из JWT.

## Фактический прогон на base

Команда (через harness, из `getting-started-python`):

```sh
sh tools/run-java-test.sh --repo ../niffler-py-st3 \
    --jdk /opt/homebrew/opt/openjdk@21 --module niffler-gateway \
    --tests 'guru.qa.niffler.controller.CategoriesControllerValidationTest' \
    --label baseline \
    --target niffler-gateway/src/main/java/guru/qa/niffler/controller/CategoriesController.java \
    --target niffler-gateway/src/main/java/guru/qa/niffler/model/CategoryJson.java
```

Выполненная Gradle-команда (из манифеста):
`sh gradlew :niffler-gateway:cleanTest :niffler-gateway:test --tests '<selector>'
--no-build-cache --rerun-tasks --no-daemon`, cwd = корень приложения.

Evidence: `artifacts/java/run-pqzz4gmr/` (manifest, gradle.log, свежий
JUnit XML, копии исходников). Манифест: `status=completed`, `exit_code=1`,
`junit.stale_or_missing=false`, `junit.summary={total:6, passed:2, failed:4,
errors:0, skipped:0}`, `cached_execution_detected=false`, commit = base SHA.
`dirty=true` — следствие untracked тестового файла, не правок продукта.
Строка `cleanTest UP-TO-DATE` в логе относится к задаче cleanTest; задача
`test` исполнена (12 actionable tasks, 11 executed) — это фактический
прогон, не NO-SOURCE/кеш.

| Случай | Вход | Ожидание | Факт на base | Результат |
| --- | --- | --- | --- | --- |
| CAT-UPD-VAL-001 | `""` | 400, нет вызова downstream | 200; `updateCategory` вызван с `name=` | FAIL (ожидаемо) |
| CAT-UPD-VAL-002 | `"   "` | 400, нет вызова | 200; вызван с `name=   ` | FAIL (ожидаемо) |
| CAT-UPD-VAL-003 | `A×1` | 400, нет вызова | 200; вызван с `name=A` | FAIL (ожидаемо) |
| CAT-UPD-VAL-004 | `A×51` | 400, нет вызова | 200; вызван с `name=A×51` | FAIL (ожидаемо) |
| CAT-UPD-VAL-005 | `A×2` | 200, точные данные | 200; captor подтвердил id/name/username/archived | PASS |
| CAT-UPD-VAL-006 | `A×50` | 200, точные данные | 200; то же | PASS |

Каждый негативный случай несёт два зафиксированных расхождения в JUnit XML:
`expected: <400> but was: <200>` и `NeverWantedButInvoked` с фактическим
`CategoryJson` в вызове `CategoriesController.updateCategory:56` — прямое
доказательство отсутствующего `@Valid`, а не побочного дефекта.

Отдельно до harness: `JAVA_HOME=... sh gradlew :niffler-gateway:compileTestJava`
→ exit 0 (компиляция теста на чистом base).

## Передача агенту 05

- Набор тестов неизменяем: ровно файл из раздела «Изменённые файлы» с
  указанными sha256/git blob. Head-прогон выполнять с той же командой
  (`--label head`); при желании `cleanTest` уже встроен, но флаги
  `--no-build-cache --rerun-tasks --no-daemon` добавляет harness сам.
- Ожидание на head: минимальный фикс `@Valid` на `@RequestBody` в
  `updateCategory` должен дать все 6 PASS (валидация доходит до
  `MethodArgumentNotValidException` → 400 без `GlobalExceptionHandler`;
  стабы в негативных тестах не объявлены, strict-stubs не помешает).
- Фактический прогон засчитывать только по свежему JUnit в манифесте
  (`files` непустые + `summary`), не по exit 0 — правило из 01/02.

## Предел доказательств

- Проверяется только gateway-контроллер с mock downstream: **не**
  доказывает сохранность данных в реальной БД, поведение spend, OAuth/JWT
  против настоящего auth и межсервисную интеграцию. R3/R4 в реальном
  окружении остаются за Python API-прогоном (агенты 03/06).
- На base невалидное имя доказано только до вызова `SpendClient`;
  факт записи в БД выведен в 00 из исходников spend и здесь
  не воспроизводился.
- Соответствие `@NotBlank`/`@Size` подтверждено косвенно: контракт
  принадлежит `CategoryJson`, и позитивные границы (2/50) уже принимаются —
  падение на 1/51/пустоте показывает именно отсутствие триггера валидации.

## Подтверждено / не проверялось

Подтверждено фактическим прогоном: компиляция теста, wiring standalone
MockMvc + validator + Jwt resolver, воспроизведение пробела валидации на
base SHA с двойным evidence на случай, свежий JUnit и сохранение exit 1
через harness.

Не проверялось (вне области 04): head-прогон с фиксом, реальный HTTP/БД/OAuth,
запуск Spring-приложения, Docker, поведение spend-сервиса, e2e-сценарии.
