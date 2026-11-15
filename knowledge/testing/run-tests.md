# Запуск и проверка тестов

Все команды ниже выполняются из корня проекта. Shell-скрипты запускаются
через `sh`; executable bit не нужен. Они сами переходят в корень проекта.
Интерпретатор выбирается так: `PYTHON` (путь к executable, без аргументов),
затем `.venv/bin/python`, затем `python3` из PATH.

## Предварительная проверка

```sh
sh tools/git.sh status
sh tools/versions.sh
sh tools/compile-tests.sh
sh tools/run-tests.sh list
```

`versions.sh` проверяет Python 3.13/3.14 и точные версии всех зависимостей
из `requirements.txt`, используя metadata установленного окружения.
Python 3.13 соответствует локальному проекту/Actions, 3.14 — описанному
Jenkins-агенту. Проверка одной версии не подтверждает другую.
Она не проверяет браузер, драйвер, сетевой доступ или наличие тестового аккаунта.
Скрипты ничего не устанавливают и не запускают сервисы.

`compile-tests.sh` проверяет версии, компилирует корневые Python-файлы,
`pages/`, `infrastructure/`, `test_data/`, `tests/`, `tools/`, затем выполняет
`pytest --collect-only`. `list` получает актуальные node ID через pytest,
а не из сохранённого списка. Сбор загружает conftest, dotenv и pytest-плагины,
но не исполняет тесты и не создаёт браузер через наши фикстуры.
Компиляция и сбор тестов не являются успешным тестовым прогоном.

## Выбор области

```sh
sh tools/run-tests.sh group unit
sh tools/run-tests.sh one 'tests/unit/test_browser.py::TestDriverFactory::test_remote_mode_uses_remote_driver'
sh tools/run-tests.sh --allow-sut group auth --browser firefox
sh tools/run-tests.sh --allow-sut one 'tests/auth/test_login.py::TestLogin::test_success_login'
sh tools/run-tests.sh --allow-sut group registration
sh tools/run-tests.sh --allow-sut group ui --browser chrome --bversion 131
sh tools/run-tests.sh --allow-sut all
```

Группы: `unit`, `api`, `auth`, `registration`, `logout`, `ui` (три UI-области).
`all` выбирает весь `tests/`, включая unit. `one` принимает настоящий node ID
в существующем файле `tests/.../test_*.py`; параметризованный ID заключай в кавычки.
При добавлении новой области обнови `GROUPS` в `tools/harness.py`; новые тесты
в существующих областях обнаруживаются pytest автоматически.

Unit-тесты используют подмены драйвера и транспорта; доступ к стенду им не нужен.
Для любого выполнения вне `tests/unit/` нужен `--allow-sut` (API и UI).
Этот флаг фиксирует уже имеющееся разрешение на выбранный стенд и сценарии,
включая постоянные записи регистрации; он не заменяет разрешения клиента
или sandbox. Учитывай разрешение из текущего запроса, повторно его не запрашивай.
Запрос на внедрение harness сам по себе не требует UI-прогона или CI-запуска.

Браузер и стенд настраиваются существующими `Settings`: `--browser`,
`--bversion`, `HEADLESS`, `BASE_URL`, `AUTH_URL`, `TIMEOUT_S`,
`SELENIUM_REMOTE`, `SELENIUM_REMOTE_URL`, `.env`. Значения секретов не печатай.
Перед UI-прогоном проверь наличие нужного аккаунта, локального браузера/драйвера
либо доступного Grid. Selenium Manager при первом старте может обратиться к сети.

Скрипты не передают произвольные pytest-флаги. Для более узкого фильтра или
специальных pytest-опций используй прямой `python -m pytest` в выбранном окружении,
с теми же требованиями к области и доступу.

## Результаты и коды завершения

Каждый запуск через `run-tests.sh` создаёт новый каталог:
`artifacts/harness/run-*/`, внутри `allure-results/`, `junit.xml` и `manifest.json`.
Точный путь печатается перед pytest. Посмотреть конкретный отчёт:

```sh
allure serve artifacts/harness/run-ИМЯ/allure-results
```

`manifest.json` (schema_version 2) сохраняется до старта pytest и обновляется
после завершения. Он содержит run_id, UTC started_at/finished_at, версию Python, commit и dirty
тестового репозитория, выбранный scope/структурные node ID, CLI-параметры браузера,
exit_code и относительные пути артефактов. Сводка `junit_summary` разделяет total,
passed, failed, errors, skipped; отсутствующий/повреждённый JUnit даёт `null`,
а не успешный результат. Состояние `completed` означает завершение команды,
в том числе с ненулевым exit code. Ошибка запуска даёт `launch_error`/127,
KeyboardInterrupt — `interrupted`/130; при принудительном убийстве процесса
может остаться `running` с незаполненным finished_at.

Если выбор затрагивает `tests/api` (группа `api`, node ID `tests/api/...` или
`all`), до старта pytest manifest заполняет `source_identity` согласованного
контракта `api-contract-v1`: `captured_at`, набор файлов с sha256/git blob/
tracked, список `copies` (физические копии — `sources/` в каталоге прогона) и
`missing` для отсутствующих файлов. После завершения `changed_during_run`
перечисляет файлы, изменившиеся или появившиеся/исчезнувшие за время прогона,
и `rechecked_at`; `null` означает, что проверка не завершилась. Для прогонов
вне `tests/api` блок равен `null`. Файлы с секретами (`.env`) не
fingerprint'ятся и не копируются никогда. При изменении набора контракта
поднимай `API_CONTRACT_VERSION` в `tools/harness.py`.

При переданных флагах окружения manifest содержит `environment`:
`declared` — декларация оператора (`app_base_sha`, `app_patch_sha256`,
`gateway_image_id`, `gateway_container`, `source: "operator"`, `captured_at`)
и `container_check` — фактический результат `docker container inspect`,
выполненный до старта pytest: `performed`, `reason`, `checked_at`,
`container_id`, `container_name`, `container_running`, `image_id`, `image_tag`,
`matches_declared_image` (декларированный ID допустим как короткий префикс).
Недоступный docker, отсутствующий контейнер и нечитаемый вывод дают
`performed=false` с явной причиной — декларация результатом не подменяется.
Полный inspect, env контейнера и credentials не сохраняются. Без флагов
`environment` равен `null`; невалидные значения отклоняет argparse с кодом 2.

Manifest не включает env, remote URL, вывод тестов, содержимое diff, имена
изменённых файлов и значения параметризации в node ID. Свободное значение
`--bversion` сохраняется только как короткая метка из букв, цифр, `._-`;
остальные значения заменяются на `<omitted>`. Неопределённые сведения Git —
`null`. CLI-значения браузера не доказывают фактическую конфигурацию из env;
commit приложения и привязка gateway-контейнера фиксируются только при явных
`--app-*`/`--gateway-*` флагах. Команды `list`, `check`, `versions` и
заблокированные до старта проверки отдельного манифеста выполнения не создают.

CI и прямые команды из README продолжают писать в `allure-results/`.
Локальные результаты harness не подхватываются автоматически Telegram-скриптом
или CI: передавай точный каталог инструментам анализа.
Скриншоты/HTML по-прежнему пишет существующий хук в `artifacts/`.

В результате укажи команду, интерпретатор/версии, область, exit code,
число passed/failed/errors/skipped и путь к материалам текущего запуска.
Сохраняй различие между failed теста и ошибками подготовки/teardown.
Сбор без выполнения, пропуски или старые результаты не подтверждают PASS.

Коды pytest сохраняются (включая 5 при отсутствии тестов); argparse возвращает
2 при неверном scope/аргументах; 69 означает неподходящий Python/зависимости,
77 — SUT-запуск без подтверждения доступа. Shell `git.sh`/`gh.sh` используют
64 для неверных аргументов. Скрипты не очищают результаты предыдущих запусков.

## API-пилот CAT-UPD-VAL

Офлайн-проверка: `sh tools/run-tests.sh group unit`.
Реальный прогон: `sh tools/run-tests.sh --allow-sut group api` — только после
готовности изолированного окружения и выбранного scope записей/очистки.
Группа `api`, отдельные API node ID и `all` требуют `--allow-sut`;
collection не обращается к приложению. Сам флаг не поднимает стенд.

Прогону следует явно придать идентичность окружения флагами `run`:

```sh
sh tools/run-tests.sh --allow-sut group api \
  --app-base-sha 36674280b6878540a9e88f40aaeedf5dfdd2e6ce \
  --app-patch-sha256 <sha256 применённого patch, если нет head SHA> \
  --gateway-image-id <image ID варианта base/fix> \
  --gateway-container <ID или имя работающего gateway-контейнера>
```

`--app-base-sha` — базовый commit приложения, `--app-patch-sha256` — SHA-256
применённого patch при отсутствии отдельного head SHA, `--gateway-image-id` —
ожидаемый Docker image ID gateway (полный или короткий hex), `--gateway-container`
— ID или имя контейнера для проверки `docker container inspect` до старта.
Невалидные значения отклоняются argparse с exit 2 до создания evidence.
Полученные `environment.declared`/`container_check` и `source_identity`
описаны в разделе «Результаты и коды завершения».

Контракт окружения: [03-runtime-plan.md](../../docs/qa-workflow/handoffs/03-runtime-plan.md).
Координатор выбрал для подготовки disposable compose-проект `catupdval`,
выделенного пользователя и параметризованный SQL DELETE только собственной
категории по ID. `API_BASE_URL`, `API_AUTH_URL`, `API_USERNAME`,
`API_PASSWORD`, `API_SPEND_DB_DSN` приходят из env; автопровижининг включается
только явным `API_USER_AUTOPROVISION=true`. Не направлять эти fixtures на общий
аккаунт или публичный стенд. OAuth/consent и SQL подтверждены реальным прогоном 07 на disposable-стеке;
новое окружение требует отдельной проверки readiness, а отсутствие настройки
остаётся ошибкой подготовки.
HTTP-слой использует stdlib, SQL — явно закреплённые psycopg/psycopg-binary.
Токены, пароли и DSN не включать в evidence.

## Java evidence для пилота

Команда выполняется из корня тестового проекта:

```sh
sh tools/run-java-test.sh --repo ../niffler-py-st3 \
  --jdk /opt/homebrew/opt/openjdk@21 --module niffler-gateway \
  --tests 'guru.qa.niffler.controller.CategoriesControllerValidationTest' \
  --label baseline \
  --target niffler-gateway/src/main/java/guru/qa/niffler/controller/CategoriesController.java \
  --target niffler-gateway/src/main/java/guru/qa/niffler/model/CategoryJson.java
```

Для повторного эксперимента после исправления используется `--label head`.
Selector разрешается в файл `src/test/java` автоматически; wildcard selectors
и нестандартные source sets могут потребовать явных `--target`.

Материалы записываются в отдельный `artifacts/java/run-*/`: manifest.json,
gradle.log, копии JUnit, исходников и ограниченный source.patch. Manifest
фиксирует версию wrapper/JDK/Python, SHA/dirty приложения, argv и exit code.
Копия нового теста и хеши целевых файлов описывают незакоммиченный эксперимент;
метка `head` не означает наличие отдельного commit SHA.

Передаются `JAVA_HOME` и существующее окружение процесса, но env целиком
в manifest не записывается. Логи, XML, исходники и patch могут содержать
данные теста: перед внешней передачей проверяй содержимое артефактов.

Harness запускает cleanTest и test с `--no-build-cache --rerun-tasks --no-daemon`.
Свежесть XML дополнительно сравнивается с snapshot до запуска.
Ненулевой baseline сохраняется. Наличие exit 0 не доказывает выполнение:
проверяй непустой список JUnit, summary с total > 0, отсутствие пропусков
в целевых случаях и `cached_execution_detected=false`. Повреждённый XML
не должен давать неполную сводку как полную; summary в таком случае — null.

Ошибки аргументов дают 2, блокировка до старта — 69 без evidence;
launch_error — 127, interrupted — 130. При прерывании дочерний запуск
останавливается до сбора итогового evidence. Обычный exit code Gradle
сохраняется. Параллельные Gradle-прогоны в одном checkout не разрешаются
координатором; harness сам по себе не является блокировкой очереди.

## CI

Для GitHub Actions см. [ci-github.md](../integrations/ci-github.md).
Jenkins описан в `README.md` и `Jenkinsfile`; его credentials не заменяются env
из локального shell. Сохраняй порядок существующего CI: выполнение тестов →
отчётность/Telegram даже при падении → итоговый статус.
