# Передача результата: готовность Java-сборки gateway

Агент: `01` (готовность сборки). Дата: 2026-11-14.
Статус: `ready` — `niffler-gateway` компилируется на base SHA без изменений
build-файлов; команда запуска теста агента 04 проверена на уровне wiring.
Успешная компиляция не является прогоном тестов; реально выполненных
тестов: 0 (в `niffler-gateway` нет `src/test`).

## Входы и версии

- Приложение `niffler-py-st3`: `HEAD = 36674280b6878540a9e88f40aaeedf5dfdd2e6ce`,
  ветка `main`, `git status --porcelain` пуст до и после всех Gradle-запусков —
  дерево чистое, чужих изменений не было и не появилось.
- JDK: `/opt/homebrew/opt/openjdk@21` → `openjdk 21.0.12.1` (Homebrew, aarch64),
  `javac 21.0.12.1`. Системная `java` (`/usr/bin/java`) — нерабочая заглушка,
  exit 1 «Unable to locate a Java Runtime»; `JAVA_HOME` обязателен — подтверждено
  воспроизведением, а не только по assessment.
- Gradle wrapper: `gradle-8.6-bin.zip` (`gradle-wrapper.properties`), дистрибутив
  скачан при первом запуске (сеть к services.gradle.org и Maven Central работает);
  JVM сборки 21.0.12.1.
- `gradle.properties`: `org.gradle.daemon=false` — каждый вызов форкает
  single-use daemon (первый холодный прогон ~44 c, тёплый ~3–4 c).
  Свойство не менялось.
- Прочитаны: `AGENTS.md` тестового проекта,
  `docs/qa-workflow/api-framework-assessment.md`,
  `docs/qa-workflow/agent-tasks/01-build-readiness.md` и `agent-tasks/README.md`.

## Изменённые файлы

- В приложении: **нет**. Все три разрешённых файла (`settings.gradle`, корневой
  `build.gradle`, `niffler-gateway/build.gradle`) оставлены без правок —
  конфигурация работает как есть. Соответственно baseline- и head-эксперименты
  автоматически используют одинаковые настройки сборки.
- В тестовом проекте: этот отчёт и логи в
  `docs/qa-workflow/handoffs/evidence/01-build-readiness/`.

## Проверка `niffler-e-2-e-tests` в settings.gradle

`settings.gradle` включает отсутствующий каталог `niffler-e-2-e-tests`.
Воспроизведено: `gradlew projects` (Gradle 8.6) завершается `BUILD SUCCESSFUL`,
exit 0, проект `:niffler-e-2-e-tests` присутствует в дереве как пустой
(без каталога и задач). Каталог при этом **не создаётся** в рабочем дереве —
после прогона `git status` по-прежнему чист. Проблема не воспроизвелась,
правка не требовалась и не вносилась.

## Выполненные команды и evidence

Все команды выполнялись из корня приложения с
`JAVA_HOME=/opt/homebrew/opt/openjdk@21`. Логи:
`docs/qa-workflow/handoffs/evidence/01-build-readiness/`.

| Команда | Exit | Результат |
| --- | --- | --- |
| `git rev-parse HEAD` + `git status --porcelain` | 0 | base SHA, дерево чисто → `agent01-versions.log` |
| `java -version` / `javac -version` (Homebrew JDK) | 0 | 21.0.12.1 → `agent01-versions.log` |
| `java -version` (системный `/usr/bin/java`, без JAVA_HOME) | 1 | stub, runtime не найден |
| `sh gradlew --version` | 0 | Gradle 8.6, JVM 21.0.12.1 → `agent01-versions.log` |
| `sh gradlew projects` | 0 | 7 проектов, `niffler-e-2-e-tests` пустой → `agent01-projects.log` |
| `sh gradlew :niffler-gateway:compileJava` | 0 | BUILD SUCCESSFUL 44 s, 8 задач → `agent01-compileJava.log` |
| `sh gradlew :niffler-gateway:test` | 0 | BUILD SUCCESSFUL, `:test NO-SOURCE` |
| `sh gradlew :niffler-gateway:test --tests 'guru.qa.niffler.controller.CategoriesControllerValidationTest'` | 0 | BUILD SUCCESSFUL, всё ещё NO-SOURCE → `agent01-test-filter.log` |
| `sh gradlew :niffler-gateway:dependencies --configuration testRuntimeClasspath` | 0 | граф разрешается → `agent01-testdeps.log` |

Подтверждено в выводе `compileJava`: генерация protobuf для
`niffler-grpc-common`, сборка его jar, XJC-генерация из `userdata.wsdl`
(non-fatal warning «Support for WSDL is experimental»), компиляция контроллеров
включая `CategoriesController` → `niffler-gateway/build/classes/java/main/`.
`build/` покрыт `.gitignore` (`**/build`) — дерево остаётся чистым.

Test classpath (`testRuntimeClasspath`) разрешается полностью:
JUnit Jupiter 5.11.4, `junit-platform-launcher` 1.11.4, Mockito 5.14.2 +
`mockito-junit-jupiter`, `spring-test` 6.2.5, xmlunit/jsonassert.
`spring-security-test` **отсутствует** — если агенту 04 понадобится
`@WithMockUser`/`SecurityMockMvcRequestPostProcessors`, потребуется одна строка
`testImplementation 'org.springframework.security:spring-security-test'` в
`niffler-gateway/build.gradle`; для standalone MockMvc с собственным
argument resolver это не нужно.

## Команда для агента 04

```sh
cd /Users/zenalark/PycharmProjects/Test-java/niffler-py-st3
JAVA_HOME=/opt/homebrew/opt/openjdk@21 sh gradlew :niffler-gateway:test \
  --tests 'guru.qa.niffler.controller.CategoriesControllerValidationTest'
```

- Тест кладётся в `niffler-gateway/src/test/java/guru/qa/niffler/controller/
  CategoriesControllerValidationTest.java` — дефолтный `src/test/java`
  sourceSet уже настроен, изменений в `build.gradle` не нужно.
- Результаты JUnit: `niffler-gateway/build/test-results/test/TEST-*.xml`;
  HTML-отчёт: `niffler-gateway/build/reports/tests/test/index.html`.
- До появления файла фильтрованный запуск даёт `NO-SOURCE` и **exit 0** —
  пустой успех нельзя принимать за прогон: проверять наличие
  `TEST-guru.qa.niffler.controller.CategoriesControllerValidationTest.xml`.
  Если файл существует, но фильтр не совпал, Gradle падает с exit 1
  «No tests found for given includes» — различие надёжно по XML, не по коду.
- Между повторными запусками с тем же входом задача `test` может уйти в
  `UP-TO-DATE`; для гарантированного прогона агенту 05:
  `... :niffler-gateway:cleanTest :niffler-gateway:test --tests '...'`
  (или `--rerun-tasks`). `cleanTest` не трогает чужие артефакты.

## Подтверждено / не проверялось

Подтверждено: чистый base SHA; компиляция gateway со всеми генераторами
(XJC, protobuf); разрешение test classpath; рабочий JDK-путь; поведение
Gradle с отсутствующим модулем; exit-коды выше.

Не проверялось (вне области 01): реальный MockMvc-тест и его компиляция
(файла нет — это работа агента 04); прогон любых тестов; запуск
Spring-приложения, Docker, OAuth, БД; сборка модулей, не являющихся
зависимостями gateway (`niffler-auth`, `niffler-spend`, `niffler-currency`,
`niffler-userdata`).

## Решения и блокеры

- Очередь Gradle соблюдена: перед запусками проверено отсутствие процессов
  Gradle в checkout; параллельных прогонов с 04/05 не было.
- `spring-security-test` — решение для координатора/агента 04, если тесту
  понадобится security-инфраструктура MockMvc (см. выше).
- `niffler-e-2-e-tests` оставлен в `settings.gradle`: безвреден на Gradle 8.6,
  но при переходе на Gradle 9+ поведение стоит перепроверить (deprecation-ноты
  уже есть в выводе сборки).
- Следующий исполнитель: агент 04 (MockMvc-тест) с командой выше; затем
  агент 05 для прогонов base → fix → head с `cleanTest` между сериями.
