# Координация второй волны CAT-UPD-VAL

Дата: 2026-11-14. Исходные незакоммиченные изменения сохранены.

## Приёмка входов 03 и 04

Оба отчёта уже существовали при возобновлении работы; повторно задачи не
запускались. 03 принят как статический план и контракт разработки fixtures,
не как подтверждение работающего окружения. 04 принят как `ready` для 05
(статус `done` в исходном handoff означает завершение именно задачи 04).

Координатор проверил manifest и JUnit `artifacts/java/run-pqzz4gmr/`:
6 случаев, 2 passed, 4 failed, 0 errors/skipped, exit 1, свежие XML,
кеш не обнаружен. SHA-256 текущего теста, контроллера и CategoryJson
совпали с сохранённым manifest. Это baseline standalone MockMvc с mock
downstream; реальная запись в БД не проверена.

## Решение по контракту 03

Для реализации 06 выбран Runbook A: отдельный disposable compose-проект
`catupdval`, Kafka включена. Перед исполнением 07 обязательны проверки
конфликтов фиксированных имён/портов и readiness; чужие ресурсы не удалять.
Образы идентифицировать по исходникам/patch и image ID: тег SHA сам по себе
не описывает незакоммиченный фикс и не заменяет сохранение patch.

Fixtures используют выделенного пользователя из env. Автосоздание разрешает
только явный `API_USER_AUTOPROVISION=true`. Контракт очистки —
параметризованный DELETE собственной категории по ID в явно настроенной
пилотной БД, затем контрольный GET; архивация очистку не заменяет.
Пользователь остаётся до удаления disposable окружения. Никаких секретов
в коде или отчёте. Это решение для подготовки кода; 06 не запускает стенд.
OAuth/consent, реальные HTTP-ответы и SQL teardown подтверждаются только в 07.

## Готовые поручения и области

- **05:** выполнить [поручение baseline → fix → повторный прогон](../agent-tasks/05-baseline-and-fix.md).
  Вход 04 проверен, очередь Gradle выделена только 05. Перед фиксом сохранить
  собственный baseline, тест не менять. Запись только в production
  `CategoriesController.java`, handoff 05 и локальные artifacts.
- **06:** выполнить [поручение Python API-тестов](../agent-tasks/06-python-api.md)
  по принятому контракту 03. Только выделенные Python-каталоги, offline
  transport/fixture-проверки и handoff 06. Реального SUT-доступа в задаче нет.
  Общие файлы, зависимости, harness и каталог интегрирует координатор.

Зависимость SQL согласована: `psycopg==3.2.13` и
`psycopg-binary==3.2.13` явно закреплены и установлены в локальный venv.
HTTP — стандартная библиотека. Группа `api` добавлена в harness;
проверка без `--allow-sut` вернула 77 до загрузки pytest.

## Следующая передача

При выполнении 05 первая sandbox-попытка `artifacts/java/run-bj_6azjz/`
остановилась на lock `~/.gradle`, тесты не выполнялись. После разрешения
доступа координатор выполнил фактический baseline:
`artifacts/java/run-l0qw8660/`, exit 1, 6 total / 2 passed / 4 failed,
0 errors/skipped, свежий JUnit и `cached_execution_detected=false`.
Этот результат передан 05 до изменения продукта; очередь Gradle возвращена 05.

05 принят: единственная production-правка — `@Valid` у request body
`updateCategory`. Повторный прогон `artifacts/java/run-36tzwapr/`:
exit 0, 6 passed, 0 failed/errors/skipped, свежий JUnit, кеш не обнаружен.
Координатор проверил хеши сохранённых исходников в обоих прогонах и
совпадение текущих файлов с head-evidence. Тест не изменён. Это
`36674280b6878540a9e88f40aaeedf5dfdd2e6ce` + patch, нового head SHA нет.
Очередь Gradle свободна. [Подробный handoff 05](05-baseline-and-fix.md).

06 принят после ревью: два параметризованных API-теста на шесть случаев,
stdlib HTTP/PKCE, отдельные fixtures, SQL cleanup по ID и username.
Каталог компонентов и команда `group api` интегрированы координатором.
При malformed POST без UUID фиксируется риск оставшихся данных; успешная
очистка не заявляется и удаление по имени не выполняется.

Итоговая Python-проверка координатора после завершения 06:
`sh tools/compile-tests.sh` — exit 0, 73 collected (без исполнения API/UI);
`sh tools/run-tests.sh group unit` — exit 0, 58 passed, 0 failed/errors/skipped.
Evidence: `artifacts/harness/run-v1bi7z1n/` (manifest, JUnit, Allure).
Python 3.13.15, pytest 9.1.1, allure-pytest 2.16.2,
psycopg/psycopg-binary 3.2.13. `git diff --check` — exit 0.

Входы 05/06 приняты, итоговая локальная проверка завершена.
Следующий исполнитель — 07 по [готовому поручению](../agent-tasks/07-integration.md).
Реальный запуск требует готовых env/credentials и установленного scope
изолированного окружения. Публикация PR и запись TestOps в эту волну не входят.

Проверка наличия переменных (без вывода значений) в окружении координатора
и локальном `.env`: `API_BASE_URL`, `API_AUTH_URL`, `API_USERNAME`,
`API_PASSWORD`, `API_SPEND_DB_DSN`, `API_USER_AUTOPROVISION` отсутствуют.
Для 07 подготовить env локально; секреты не передавать в чат/handoff.
