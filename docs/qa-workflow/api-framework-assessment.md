# API-фреймворк и окружение для пилота

Дата: 2026-11-14. Анализ статический: Gradle, Docker daemon, приложение,
OAuth и обращения к БД не запускались. Секреты из env-файлов не читались.

## Версии источников

| Источник | Commit |
| --- | --- |
| `niffler-py-st3/main` | `36674280b6878540a9e88f40aaeedf5dfdd2e6ce` |
| `origin/study_AL_12_oauth` | `7b1274408ff5959ccccf1d154325c077c00fbe09` |
| `origin/study_AL_14_unit` | `89833180db76ac4923dcb6338a6bb9d996e9373f` |
| `origin/study_AL_14_kafka` | `2b7e0bba7737940843ec48e72331726d6bd10223` |

Удалённые ветки прочитаны через `git show`, без checkout или изменения
репозитория приложения. Локальная копия приложения расположена в соседнем
каталоге `../niffler-py-st3` относительно корня тестового проекта.

## Выбор места API-автотестов

Рекомендуемое место Python API-пилота — текущий `getting-started-python`:
`tests/api/` со своими fixtures, транспортом в `infrastructure/http/`,
фиксированными входами в `test_data/consts/`. Это предложение структуры,
каталоги и API-зависимости ещё не добавлены.

Здесь уже есть актуальные правила, воспроизводимые команды, учёт артефактов,
Allure, CI и разделение общих компонентов. В `requirements.txt` сейчас нет
явно объявленного HTTP-клиента, Pydantic, SQLModel или PKCE-библиотеки.
Зависимости для API следует добавлять явно и минимально, а не полагаться
на транзитивные пакеты Selenium.

Учебный `niffler-tests-python` использовать как источник отдельных идей и
контрактов. Полный перенос добавит связность с браузером, OAuth, БД,
отчётностью и множеством зависимостей, которые для первого пилота не нужны.
Переключение приложения на учебную ветку только ради автотестов не требуется.

Для запуска будущей группы `api` потребуется отдельно обновить harness и
каталог компонентов. Удалённый SUT должен требовать тот же явный scope доступа,
что и существующие сценарии. Автозапуск браузера в API fixtures не нужен.

## Что можно переиспользовать и что требуется исправить

| Область | Наблюдение | Решение для пилота |
| --- | --- | --- |
| HTTP-клиент | `SpendsHttpClient` покрывает GET/POST категорий и расходы, но не PATCH категории; методы сразу преобразуют JSON в модель | Реализовать минимальные операции GET/POST/PATCH с доступом к статусу и телу ответа, включая ожидаемый 400 |
| Статусы | В `12_oauth` ошибки HTTP обрабатываются непоследовательно; в `14_kafka` вызов `raise_for_status` закомментирован | Явно проверять ожидаемый статус в тесте до чтения успешной DTO; отрицательные ответы не преобразовывать в Category |
| Отчётность | `allure_attach_request` в `14_kafka` дважды вызывает обёрнутую функцию HTTP-запроса | Не переносить; один вызов транспорта, отдельное безопасное формирование вложений |
| OAuth | PKCE-пара вычисляется, но в `/authorize` передаётся `self.session.code`, а не `self.code_challenge`; code из redirect сохраняется списком | Не считать готовым; проверить protocol flow и обработку ошибок до переиспользования |
| Авторизация API | `spends_client` зависит от `auth_front_token`; в API conftest есть браузерные autouse fixtures | Изолировать API credentials и token fixture от UI, не открывать браузер для API-проверки |
| Модели | DTO и SQLModel смешаны; у части полей `Optional` нет значения по умолчанию | Для пилота достаточно минимального JSON-контракта; ORM не подключать ради представления ответа |
| Данные | Фикстура category удаляет запись через БД; её имя и запросы местами привязаны к общим пользователям | Отдельная категория для сценария, очистка только её ID; готовность DB-доступа не предполагается |
| DB-поиск | `get_user_categories_by_name` использует Python `and` между SQL-условиями | Перед переиспользованием заменить корректной композицией SQL predicates и проверить изоляцию пользователя |
| Unit-проверки | В `14_unit` есть проверки клиента на mock response и cleanup генераторов | Полезные примеры, но не доказательство работоспособности реального OAuth/HTTP/DB |

Дополнительно найдено сохранение token во вложении, захардкоженные credentials
в фикстуре и вложение сырого curl. Значения в этот документ не переносятся.
В новом слое credentials читаются из окружения; токены, cookies и пароли
редактируются перед отчётностью. Request logging не должен менять поведение
или количество запросов.

Основные первоисточники на фиксированных версиях:

- [SpendsHttpClient](https://github.com/L4m4w/niffler-py-st3/blob/2b7e0bba7737940843ec48e72331726d6bd10223/niffler-tests-python/clients/spends_client.py)
- [OAuthClient](https://github.com/L4m4w/niffler-py-st3/blob/2b7e0bba7737940843ec48e72331726d6bd10223/niffler-tests-python/clients/oauth_client.py)
- [HTTP sessions](https://github.com/L4m4w/niffler-py-st3/blob/2b7e0bba7737940843ec48e72331726d6bd10223/niffler-tests-python/utils/sessions.py)
- [Request attachments](https://github.com/L4m4w/niffler-py-st3/blob/2b7e0bba7737940843ec48e72331726d6bd10223/niffler-tests-python/utils/allure_helpers.py)
- [API fixtures](https://github.com/L4m4w/niffler-py-st3/blob/2b7e0bba7737940843ec48e72331726d6bd10223/niffler-tests-python/tests/api/web/conftest.py)
- [SpendDB](https://github.com/L4m4w/niffler-py-st3/blob/2b7e0bba7737940843ec48e72331726d6bd10223/niffler-tests-python/database/spend_db.py)

Доказательство двойного запроса: в функции `allure_attach_request.wrapper`
на указанном SHA вызов `function(*args, **kwargs)` находится на
[строке 17](https://github.com/L4m4w/niffler-py-st3/blob/2b7e0bba7737940843ec48e72331726d6bd10223/niffler-tests-python/utils/allure_helpers.py#L17)
и повторяется на
[строке 28](https://github.com/L4m4w/niffler-py-st3/blob/2b7e0bba7737940843ec48e72331726d6bd10223/niffler-tests-python/utils/allure_helpers.py#L28)
без ветвления между ними. Оба вызова относятся к одному входу в wrapper,
если первый запрос и формирование curl не завершились исключением.

## Минимальное локальное воспроизведение в Java

Пилот затрагивает публичный gateway endpoint. Проверка только
`niffler-spend` не воспроизводит отсутствие `@Valid` в gateway.

Самый короткий первый эксперимент — standalone MockMvc-тест реального
`CategoriesController` в модуле `niffler-gateway`, с настоящим Bean Validation
и mock `SpendClient`. JWT principal передаётся тестовым argument resolver.
Не требуется поднимать SpringBoot-приложение целиком, получать JWT из auth,
подключаться к Kafka, PostgreSQL, Vault или публичному стенду.

Проверка до и после изменения:

1. Подготовить валидный JWT principal, category ID и mock успешного downstream.
2. Выполнить PATCH с пустым/коротким/длинным именем; ожидать HTTP 400.
3. Для невалидного запроса проверить отсутствие вызова `SpendClient.updateCategory`.
4. Для валидных границ проверить вызов downstream с нужными данными и ответ 200.
5. На исходной реализации отсутствие валидации должно проявиться в падении
   отрицательных проверок; после добавления `@Valid` — в их успехе.

Это предлагаемый эксперимент, пока не выполненный. Он доказывает HTTP binding,
валидацию и отсутствие downstream-записи на gateway при отказе. Он не доказывает
состояние настоящей БД, OAuth, маршрутизацию или совместимость сервисов.
Требование «данные остались прежними» затем проверяется Python API-тестом:
создать отдельную категорию → PATCH → GET той же категории по ID → сравнить
имя и остальные поля → очистить только созданные данные.

Контроллер и контракт:
[CategoriesController](https://github.com/L4m4w/niffler-py-st3/blob/36674280b6878540a9e88f40aaeedf5dfdd2e6ce/niffler-gateway/src/main/java/guru/qa/niffler/controller/CategoriesController.java),
[CategoryJson](https://github.com/L4m4w/niffler-py-st3/blob/36674280b6878540a9e88f40aaeedf5dfdd2e6ce/niffler-gateway/src/main/java/guru/qa/niffler/model/CategoryJson.java).

## Готовность сборки и ограничения

- `java -version` через системный PATH не находит Java Runtime. Дополнительная
  проверка основного агента обнаружила Homebrew JDK 21.0.12.1 в
  `/opt/homebrew/opt/openjdk@21`; прямые вызовы `bin/java -version` и
  `bin/javac -version` прошли успешно. Для сборки использовать этот JDK через
  `JAVA_HOME`, не системную заглушку. JBR 25 внутри PyCharm также обнаружен,
  но не выбран для проекта Java 21.
- Docker CLI присутствует; это не подтверждает доступность daemon или образов.
- `settings.gradle` включает отсутствующий каталог `niffler-e-2-e-tests`.
  В зависимости от Gradle это может дать пустой проект или ошибку; настройки
  следует проверить до выполнения build/скриптов. Результата Gradle пока нет.
- У gateway есть `spring-boot-starter-test` и validation starter; сборка также
  включает `niffler-grpc-common`, генерацию protobuf и JAXB/XJC. Первый запуск
  потребует доступных зависимостей Gradle/Maven и wrapper distribution.
- В gateway нет отдельного `application-test.yaml`. Standalone MockMvc выбран,
  чтобы первый эксперимент не зависел от полной конфигурации приложения.
- H2 test profile в spend пригоден для локальных service/controller проверок,
  но сам по себе не предоставляет HTTP gateway или OAuth.
- `docker-compose-dev.sh` и `docker-compose-e2e.sh` имеют глобальную очистку
  Docker-контейнеров/образов. Для пилота они не подходят без переработки scope.
- Для полного Python API-прогона ещё нужны SHA-привязанная сборка, изолированные
  данные, рабочая авторизация и ограниченный способ очистки.

## Следующие команды после подготовки

Команды ниже — план, они не выполнялись. Перед запуском нужны выбранный JDK 21,
проверенная конфигурация модулей, доступ к зависимостям и добавленный тест
`CategoriesControllerValidationTest`. Выполнять из репозитория приложения.

```sh
JAVA_HOME=/opt/homebrew/opt/openjdk@21 sh gradlew --version
JAVA_HOME=/opt/homebrew/opt/openjdk@21 sh gradlew projects
JAVA_HOME=/opt/homebrew/opt/openjdk@21 sh gradlew :niffler-gateway:test --tests 'guru.qa.niffler.controller.CategoriesControllerValidationTest'
```

Последний тест сначала запускается на исходном SHA, затем на версии
с исправлением. Для каждого запуска сохраняются SHA приложения, команда,
exit code и JUnit XML из `niffler-gateway/build/test-results/test/`.
Проверка проекта и сбор зависимостей не считаются выполненным тестом.
