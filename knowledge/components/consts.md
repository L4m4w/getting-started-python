# Константы

API-пилот: `test_data.consts.category_update` содержит `INVALID_NAMES`,
`VALID_NAMES`, `INVALID_IDS`, `VALID_IDS` (параметры и scenario IDs),
`TESTOPS_ALLURE_IDS` (согласованный scenario ID → TestOps case ID проекта 5444)
и производный `TESTOPS_ALLURE_ID_BY_NAME` (значение параметра name → ALLURE_ID
для runtime-разметки), `SNAPSHOT_FIELDS`, `CATEGORY_NAME_PREFIX`,
`MAX_ACTIVE_CATEGORIES`, `OAUTH_CLIENT_ID`, `OAUTH_REDIRECT_URI`, `OAUTH_SCOPE`
и фиктивные offline-данные `UNIT_*`. Пример:
`allure.dynamic.label("ALLURE_ID", TESTOPS_ALLURE_ID_BY_NAME[name])`.
Credentials в этот модуль не входят.

Фиксированные входы и ожидания Java evidence unit-тестов находятся в
`test_data.consts.java_evidence`: `TEST_CLASS`, `TEST_FILE_RELPATH`,
`TARGET_RELPATH`, `EXPECTED_COMMAND`, `JUNIT_GRADLE`, `EXPECTED_SUMMARY`.
Пример: `java_evidence.resolve_test_file(repo, MODULE, TEST_CLASS)`.

Фиктивные входы TestOps unit-тестов — `test_data.consts.testops`:
`ENDPOINT`, `PROJECT_ID`, `EXECUTION_ID`, `LAUNCH_ID`, `BOUND_IDS`,
`ALLURECTL_PATH`, `TOKEN_ENV`, коды выхода. Реальных TestOps ID и секретов
нет. Пример: `testops.cmd_assign(_options(env, bindings=[...]), _parser())`.

[Оглавление каталога](README.md)

В `test_data/consts/` размещаются фиксированные данные для тестов, функций
и классов: входные значения, ожидаемые результаты и наборы параметризации.
Локаторы, названия Allure-шагов и технические параметры остаются
в соответствующих компонентах. Ниже указаны текущие пути существующих констант.

| Компонент | Путь импорта | Назначение | Пример использования |
| --- | --- | --- | --- |
| `WRONG_PASSWORD`, `BAD_CREDENTIALS_ERRORS` | `test_data.consts.auth` | Неверный пароль и допустимые тексты ошибки кредов (en/ru) | `assert error in BAD_CREDENTIALS_ERRORS` |
| `HISTORY_HEADER_TEXT` | `test_data.consts.main_page` | Ожидаемый заголовок истории трат | `assert main_page.history_header_text() == HISTORY_HEADER_TEXT` |
| `REGISTRATION_SUCCESS_MESSAGE`, `PASSWORDS_MISMATCH_ERROR`, `MISMATCHED_PASSWORD_SUFFIX`, `USERNAME_TAKEN_ERROR_TEMPLATE` | `test_data.consts.registration` | Ожидаемые сообщения и входные данные тестов регистрации | `assert register_page.error_text() == USERNAME_TAKEN_ERROR_TEMPLATE.format(name)` |
| `USERNAME_PREFIX`, `USERNAME_SUFFIX_LENGTH`, `PASSWORD_LENGTH` | `test_data.consts.users` | Параметры генерации уникальных пользователей | Используются в `test_data.utils.users.unique_username` |
| `EMPTY_ENV`, `ENV_*`, `CLI_*`, `EXPECTED_*`, `ERROR_PATTERN_*`, `UNSUPPORTED_BROWSER` | `test_data.consts.settings_data` | Входные env (read-only через `MappingProxyType`) и ожидаемые значения `tests/unit/test_settings.py` | `load_settings(env=ENV_BROWSER_FIREFOX) == EXPECTED_BROWSER_FIREFOX` |
| `TEST_BASE_URL`, `TEST_AUTH_URL`, `TEST_TIMEOUT_S`, `TEST_BROWSER`, `TEST_REMOTE_URL`, `LOCAL_BROWSERS`, `SETUP_ERROR_TEXT`, `QUIT_ERROR_TEXT`, `TEST_ERROR_TEXT` | `test_data.consts.browser` | Примеры настроек и тексты ошибок подмен для `tests/unit/test_browser.py` и `infrastructure.browser.testing.make_test_settings` | `create_driver(make_test_settings(remote_url=TEST_REMOTE_URL))` |
| `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_API_URL`, `HTTP_STATUS_OK`, `RUN_INFO`, `STATS_ALL_PASSED`, `STATS_MIXED`, `STATS_MIXED_TOTAL`, `STATS_MIXED_FAILED`, `SCREENSHOT_BYTES`, `PAGE_SOURCE_HTML`, `ARTIFACT_ERROR_TEXT`, `SEND_ERROR_TEXT` | `test_data.consts.reporting` | Подменные креды (не реальные), наборы статистики (`MappingProxyType`) и payload'ы артефактов для `tests/unit/test_reporting.py` | `send_message(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, "text")` |
| `ENV_USERNAME`, `ENV_PASSWORD` | `test_data.utils.users.ENV_USERNAME`, `test_data.utils.users.ENV_PASSWORD` | Имена переменных окружения для учётных данных | `env = {ENV_USERNAME: name, ENV_PASSWORD: password}` |
| `REPOSITORY_STATE`, `UNIT_SELECTION`, `API_SELECTION`, `PRIVATE_*`, `UNSAFE_BROWSER_VERSION`, `JUNIT_*`, `EXPECTED_*`, `*_EXIT_CODE`, `LAUNCH_FAILURE_CASES`, `API_CONTRACT_SOURCES`, `MISSING_CONTRACT_SOURCE`, `ENV_FILENAME`, `APP_*`, `GATEWAY_*`, `CONTAINER_ID`, `IMAGE_*`, `DOCKER_INSPECT`, `*_STDERR`, `INVALID_*` | `test_data.consts.harness` | Подменные сведения репозитория, чувствительные значения, JUnit, контрактные исходники API и ответ docker inspect для unit-проверок harness без сети, браузера и docker | `manifest["junit_summary"] == EXPECTED_SUMMARY` |
| `WINDOW_WIDTH`, `WINDOW_HEIGHT` | `infrastructure.browser.factory.WINDOW_WIDTH` | Размер окна браузера | `assert drv.window_size == (WINDOW_WIDTH, WINDOW_HEIGHT)` |


Фиктивные данные строгой сборки — `test_data.consts.testops_package_integrity`:
входные Allure payloads и `EXPECTED_*` digest. Пример: импорт `EXPECTED_*` для проверки детерминированной сборки.

Фиктивные данные lifecycle — `test_data.consts.testops_lifecycle`:
`LAUNCH_EMPTY`, `LAUNCH_MATCHING`, `LAUNCH_PARTIAL`, `RESULTS_MATCHING_BIND`,
`DEAD_PID`, scenario/status/bindings. Пример: подмена `get_launch` ответом
`LAUNCH_EMPTY`; это не доказывает серверную обработку.


REST fixtures — `test_data.consts.testops_rest`: `TOKEN_OK`, `LAUNCH`,
`PROGRESS_READY`, `STATISTIC`, `PAGE0_FULL`, `PAGE1_LAST` и некорректные
Page-варианты; все credentials/ID фиктивные. Пример: подмена HTTP
`GET /api/testresult` страницами `PAGES_TWO`.

Verification fixtures — `test_data.consts.testops_verification`:
`SCENARIO_STATUSES`, `BOUND_IDS`, `SID_LOOKALIKE`, `UNPROVEN_PAGINATION`,
`result_row`, `rows`, `snapshot`. Пример: `snapshot(ready=False)` для
проверки запрета подтверждения незавершённой обработки.

Фиктивные входы оркестратора — `test_data.consts.workflow`: `PILOT_ID`,
`APP_REPO`/`APP_REPO_KEY`/`APP_REPO_SSH` (нормализация repo key), фиктивные
`APP_*_SHA*` (раздельные `APP_BASE_SHA`, `APP_HEAD_COMMIT_SHA`, `APP_PATCH_SHA256`,
`NON_COMMIT_OBJECT_SHA`, `WRONG_TREE_COMMIT_SHA`), `TESTS_COMMIT*`,
`REQUIREMENT_*`, `SCENARIO_*`, `BASE_SCENARIO_IDS`, `UNIT_SCENARIO_INDEX`,
`UNIT_DISPLAY_TITLES`, `BINDINGS`, `CONTEXT_SOURCE_PATHS`, `EXECUTION_*`,
`TESTOPS_*`, `EXPECTED_EXECUTIONS`, `STRENGTH_EVIDENCE`, `*_JUNIT`.
Реальных SHA/ID и секретов нет. Пример:
`project.init(app_base_sha=C.APP_BASE_SHA)`. Helpers сборки fake-проекта —
`test_data.utils.workflow` (`Project`, `FakeRunner`, `FakeGit`,
`unit_scenario_contract`, `write_manifest`, `write_raw_allure_results`,
`make_testops_state`, `testops_local_handlers`, `harness_run`, `on_testops`,
`set_upload_status`); см. [workflow.md](workflow.md).

Данные регрессий 21R-A — `test_data.consts.workflow_21r_a`:
`WEAK_REQUIRED_VALUES`, `WEAK_REQUIRED_PATHS`, `CORRUPT_REVISION_DATA`,
`CORRUPT_EXECUTION_FIELDS`, `PUBLICATION_TAMPERS`, `BAD_TESTOPS_IDS`,
`GOOD_TESTOPS_IDS`. Только синтетические входы schema/envelopes.
Пример: `@pytest.mark.parametrize("testops_id", A.BAD_TESTOPS_IDS)`.

Данные регрессий 21R-B — `test_data.consts.workflow_21r_b`:
`EXECUTION_HEAD_2`, `EXECUTION_BASE_2`, `EXECUTION_HEAD_3`,
`PR_CREATED_NUMBER`, `PR_PARENT_NUMBER`, `PR_URL_TEMPLATE`,
`HEAD_BRANCH`, `BASE_BRANCH`, `CORRUPT_STATE_BYTES`, `MUTATED_SOURCE_TEXT`,
`PROVENANCE_A`, `PROVENANCE_B` и фиктивные заголовки spec.
Пример: `ref = _mk_ref(spec, number=B.PR_PARENT_NUMBER)` в unit-регрессии;
реальных PR/секретов нет.

Данные регрессий 21R2 — `test_data.consts.workflow_21r2`:
`APP_BASE_SHA_3`/`APP_HEAD_COMMIT_SHA_3` (третья линия
grandparent→parent→child), `PR_LINEAGE_NUMBER`, `PR_TERMINAL_NUMBER`
(записанные номера remote PR в ancestry) и `EXECUTION_HEAD_4`/
`EXECUTION_HEAD_5`/`EXECUTION_BASE_3`/`EXECUTION_BASE_4` для повторного
доведения новых линий одного проекта до executed.
Пример: `get_map={(spec["repo"], R2.PR_LINEAGE_NUMBER): ref}`; фиктивные
значения, реальных PR/секретов нет.

Данные CLI-проверок `--pr-transport github` (22C) —
`test_data.consts.workflow_github_cli`: канонические фиктивные repo keys
`APP_REPO_KEY`/`TESTS_REPO_KEY` (`github.com/Unit-*`), `PR_TITLE`,
`HEAD_BRANCH`/`BASE_BRANCH`, `PR_NUMBER`/`PR_URL`/`TESTS_PR_URL`,
`BODY_TEXT`, `UNIT_TOKEN` (не реальный), имена env-переменных
`SCENARIO_ENV`/`LOG_ENV` и `SITECUSTOMIZE` — offline bootstrap для
subprocess-прогонов production `tools/workflow.py`: подменяет только
http-слой `GitHubPrTransport` и `GitReadAdapter` по JSON-сценарию и
считает credential-чтения; endpoint остаётся `api.github.com`, флагов
отключения guard'ов не добавляет. Пример:
`env, log = _env(tmp_path, scenario)` в
`tests/unit/test_workflow_github_cli.py`.


Данные clean-revision routing regressions —
`test_data.consts.workflow_tests_repo`: `TESTS_REPO`, `TESTS_REPO_KEY`,
accepted spellings, `TESTS_REPO_OTHER_KEY`, `INVALID_TESTS_REPO_INPUTS`,
`TRAVERSAL_TESTS_REPO_INPUTS`. Только synthetic repo inputs; пример:
`@pytest.mark.parametrize("value", RC.TRAVERSAL_TESTS_REPO_INPUTS)`.

`test_data.consts.workflow_historical_root` содержит synthetic execution IDs,
root names, forbidden path/member names и forged digest для containment/
external-root no-write regressions. Пример:
`ext_root = tmp_path / HR.EXTERNAL_ROOT_NAME` в unit fixture.
