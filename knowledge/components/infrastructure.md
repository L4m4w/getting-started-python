# Инфраструктурные helpers

[Оглавление каталога](README.md)

Новые общие компоненты размещаются по назначению:

| Директория | Назначение |
| --- | --- |
| `infrastructure/browser/` | Создание и настройка браузера и WebDriver |
| `infrastructure/waits/` | Общие механизмы явных ожиданий |
| `infrastructure/reporting/` | Отчётность и вложения |
| `infrastructure/http/` | API-транспорт и авторизация пилота |

| Компонент | Путь импорта | Назначение | Пример использования |
| --- | --- | --- | --- |
| `load_settings` | `settings.load_settings` | Сбор и валидация `Settings` по приоритету CLI > env > дефолты: алиас `chromium`→`chrome`, нормализация URL, ошибки при неподдерживаемом браузере, remote без URL и невалидном `TIMEOUT_S` | `settings_obj = load_settings(browser_option="firefox")` |
| `create_driver` | `infrastructure.browser.factory.create_driver` | Создать Remote/Chrome/Firefox драйвер и настроить окно по Settings. Сбой обязательной настройки прерывает подготовку: драйвер закрывается, исходная ошибка передаётся вызывающему коду; ошибка `quit()` добавляется к ней через `add_note` | `drv = create_driver(settings)` |
| `make_test_settings` | `infrastructure.browser.testing.make_test_settings` | Settings со значениями по умолчанию для unit-тестов; примеры значений — `test_data.consts.browser` | `s = make_test_settings(browser="firefox")` |
| `ElementWaits` | `infrastructure.waits.ElementWaits` | Явные ожидания для Page Object: `visible`, `clickable`, `present`, `url_contains`, `until` | `self.wait.visible(locator)` |
| `save_failure_artifacts` | `infrastructure.reporting.artifacts.save_failure_artifacts` | Скриншот и page source упавшего теста в каталог и Allure. Сбои каталога и артефактов диагностируются `warnings.warn` и не подменяют исходное падение теста | `save_failure_artifacts(drv, ARTIFACTS_DIR, name)` |
| `collect_stats` | `infrastructure.reporting.stats.collect_stats` | Счётчики passed/failed/broken/skipped по allure-results; нечитаемые файлы пропускаются | `stats = collect_stats(Path("allure-results"))` |
| `format_message` | `infrastructure.reporting.telegram.format_message` | Markdown-сообщение о прогоне по статистике и сведениям запуска | `text = format_message(stats, repo, branch, commit, trigger)` |
| `send_message` | `infrastructure.reporting.telegram.send_message` | Отправка через Telegram Bot API; при ошибке транспорта бросает `TelegramSendError` с замаскированным токеном | `send_message(token, chat_id, text)` |
| `TelegramSendError` | `infrastructure.reporting.telegram.TelegramSendError` | Ошибка отправки уведомления; текст не содержит секретов | `pytest.raises(TelegramSendError)` |

Корневой `notify_telegram.py` остаётся CLI-точкой входа для CI и делегирует
`infrastructure.reporting`: без секретов или при сбое отправки возвращает 0.
Хук `pytest_runtest_makereport` в `conftest.py` остаётся точкой подключения
артефактов к pytest.

## Локальные CLI-инструменты harness

Это shell/Python-точки входа для агента, а не helpers Page Object.
Полный контракт: [run-tests.md](../testing/run-tests.md).

| Компонент | Путь / вызов | Назначение | Пример использования |
| --- | --- | --- | --- |
| Выбор Python | `tools/_python.sh` (внутренний, source из entry point) | `PYTHON` → проектный venv → `python3`; переход в корень | `PYTHON=/path/to/python sh tools/versions.sh` |
| Проверка окружения | `tools/versions.sh` → `tools/harness.py versions` | Python 3.13/3.14 и точные установленные версии requirements | `sh tools/versions.sh` |
| Проверка исходников | `tools/compile-tests.sh` → `tools/harness.py check` | Версии, компиляция рабочих Python-каталогов, pytest collection | `sh tools/compile-tests.sh` |
| Выбор и запуск тестов | `tools/run-tests.sh` → `tools/harness.py run` | Динамический список node ID, группы/один тест, отдельные Allure/JUnit и manifest.json на запуск; API/UI требуют `--allow-sut`. Для выбора в `tests/api` manifest фиксирует `source_identity` контракта `api-contract-v1` (хеши/копии до старта, `changed_during_run` после); флаги `--app-base-sha`, `--app-patch-sha256`, `--gateway-image-id`, `--gateway-container` записывают декларацию окружения и результат проверки `docker container inspect` | `sh tools/run-tests.sh group unit` |
| Чтение Git | `tools/git.sh` | Status, diff (включая staged), whitespace check без commit/push/reset | `sh tools/git.sh diff` |
| Java evidence | `tools/run-java-test.sh` → `tools/java_evidence.py` | Один Gradle test selector с выбранным JDK, отдельные manifest/JUnit/log и копии целевых исходников в `artifacts/java/run-*` | `sh tools/run-java-test.sh --repo ../niffler-py-st3 --jdk /opt/homebrew/opt/openjdk@21 --module niffler-gateway --tests 'guru.qa.niffler.controller.CategoriesControllerValidationTest' --label baseline` |
| GitHub Actions CLI | `tools/gh.sh` | Список запусков/логи; явный флаг для rerun/dispatch; см. [контракт](../integrations/ci-github.md) | `GITHUB_REPOSITORY=owner/repo sh tools/gh.sh runs` |
| TestOps план/загрузка | `tools/run-testops.sh` → `tools/testops.py` + `infrastructure.reporting.testops` | Offline plan/status/assign/package результатов прогона в `artifacts/testops/<execution>/`; `resolve`/`verify` read-only с `--online`, `upload` только с `--execute`; см. [runbook](../integrations/testops.md) | `sh tools/run-testops.sh plan --results artifacts/harness/run-XXXX/allure-results` |
| Workflow-оркестратор | `tools/run-workflow.sh` → `tools/workflow.py` + `infrastructure.workflow` | Минимальный offline-оркестратор этапов QA workflow: versioned state в `artifacts/workflow/`, envelope-валидация артефактов, gate'ы фаз, intents перед внешними вызовами, адаптеры к harness/TestOps; live PR-транспорт не поставляется; см. [runbook](../integrations/qa-workflow.md) и [каталог](workflow.md) | `sh tools/run-workflow.sh status` |

`tools/harness.py` — внутренняя реализация CLI, не публичный Python API.
При новой области тестов обнови `GROUPS`; при смене Python в CI проверь
допустимые версии в `versions()` и инструкцию запуска. Pins читаются из
`requirements.txt`, отдельного списка версий в harness нет.

## HTTP и OAuth пилота

| Компонент | Путь импорта | Назначение | Пример использования |
| --- | --- | --- | --- |
| `HttpClient`, `HttpResponse` | `infrastructure.http.client` | HTTP через stdlib с cookies и без автоматических redirect/retry; один вызов — один запрос, статус проверяется до JSON | `response = HttpClient(origin).request("GET", "/api/categories/all")` |
| `CategoriesApi` | `infrastructure.http.client` | Авторизованные GET all, POST add, PATCH update; отрицательный ответ возвращается как данные | `response = CategoriesApi(client, token).update(snapshot)` |
| `require_status`, `PreparationError` | `infrastructure.http.client` | Проверка статуса/ошибка подготовки без секретного payload | `body = require_status(response, 200, "GET categories").json()` |
| `obtain_token`, `register` | `infrastructure.http.oauth` | Authorization code + PKCE с login/consent; явная регистрация выделенного пользователя. Callback frontend не запрашивается | `token = obtain_token(auth_client, username, password)` |

OAuth и SQL cleanup проверены офлайн и в реальном API-прогоне 07 на
disposable-стеке (см. handoff 07 и ограничения evidence в третьей волне).
Значения токенов/паролей/DSN не сохранять в отчётах.


## Проверка пакета и lifecycle TestOps

| Компонент | Путь импорта | Назначение | Пример |
| --- | --- | --- | --- |
| `ResultsIntegrityError`, `scan_assignments`, `validate_attachments` | `infrastructure.reporting.testops.results` | Строгий scan UUID/mapping и всех result/container вложений | `scan_assignments(source, index)` |
| `build_package_verified`, `assignments_digest`, `verify_package`, `verify_source_digest` | `infrastructure.reporting.testops.results` | Атомарная сборка с ожидаемым digest, идентичность mapping, проверки перед upload | `build_package_verified(source, dest, expected_digest=sha, assignments=mapping, index=index)` |
| `ExecutionLock`, `perform_upload`, `perform_verify` | `infrastructure.reporting.testops.lifecycle` | Блокировка execution, sent/unknown вместо ложного успеха, инъекция транспорта | `perform_verify(state_dir, transport)` |
| `load_state`, `StateCorruptError`, `record_package`, `expected_scenarios`, `expected_stats` | `infrastructure.reporting.testops.state` | Schema 2, явная ошибка повреждения, сохранение input/assignment/package digest | `state = load_state(state_dir)` |
| `begin_upload_attempt`, `set_attempt_phase`, `complete_attempt`, `decide_upload` | `infrastructure.reporting.testops.state` (первые три), `infrastructure.reporting.testops.lifecycle` (последний) | Долговечные границы попыток и запрет слепого retry | `decide_upload(state, retry=False)` |
| `adopt_launch`, `abandon_launch`, `resolve_in_progress`, `record_confirmation`, `mark_upload_confirmed` | `infrastructure.reporting.testops.state` | Операторское восстановление с аудитом после отдельной сверки | `resolve_in_progress(state, note)` |
| `parse_launch`, `parse_launch_results`, `launch_list_args` | `infrastructure.reporting.testops.client` | Защитный разбор read-only ответов; per-result парсер доступен; REST путь см. ниже | `parse_launch(output)` |
| `load_environment`, `AllurectlTransport` | `tools.testops` | Корневой .env с exported precedence; адаптер CLI к lifecycle | `load_environment()` |


## REST verification TestOps

| Компонент | Путь импорта | Назначение | Пример |
| --- | --- | --- | --- |
| `RestProbe`, `UrllibHttp` | `infrastructure.reporting.testops.rest` | Read-only снимок launch; token exchange внутри процесса, строгий Page walk, allowlist и drift check; HTTP слой инъецируется | `RestProbe(token).read_snapshot(endpoint, launch_id)` |
| `Assessment`, `evaluate_snapshot` | `infrastructure.reporting.testops.verification` | Чистая сверка снимка с ожидаемыми статусами и согласованными case ID | `evaluate_snapshot(snapshot, expected, launch_id=lid, project_id=pid)` |
| `perform_snapshot_verify` | `infrastructure.reporting.testops.verification` | Lock/load/probe/verdict/save; только полный bind подтверждает uploaded; empty не разрешает retry | `perform_snapshot_verify(state_dir, probe)` |

CLI: `verify --online --transport rest` выбирает REST явно; default —
allurectl. Оба пути проверяют package/source и связь с записанной отправкой.
