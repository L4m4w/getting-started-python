# Запуск и проверка

Команды выполняются из корня проекта. Используйте существующую подходящую среду;
харнесс не устанавливает зависимости. `PYTHON` задаёт интерпретатор для scripts,
по умолчанию python3. Установка, UI-прогон и внешние операции должны соответствовать
поручению пользователя и уже данным разрешениям.

```sh
sh tools/versions.sh local
sh tools/compile-tests.sh
sh tools/run-tests.sh list
```

compile-tests проверяет синтаксис conftest, notify_telegram, pages и tests через AST,
затем выполняет pytest --collect-only. Collection импортирует conftest и plugins,
читает dotenv; это не sandbox и не выполнение UI-сценариев. Текущий набор — 9 тестов.

После разрешения на нужный стенд/scope:

```sh
sh tools/run-tests.sh --allow-sut one login-success
sh tools/run-tests.sh --allow-sut group auth
sh tools/run-tests.sh --allow-sut all
```

--allow-sut — явный флаг выбранного запуска, не замена разрешений среды.
Успешная регистрация создаёт серверный аккаунт. Учитывайте отдельно BASE_URL и AUTH_URL.
Параметры chrome/firefox/headless/remote берутся из текущего conftest/env.
Для специальных параметров используйте прямую команду, например:

```sh
python3 -m pytest tests/auth/test_login.py::TestLogin::test_success_login --browser=firefox --alluredir=allure-results
```

Скрипт использует реальные node IDs. При добавлении/переименовании тестов обновите
его map; новые tests не появляются автоматически в one/list. all собирает весь tests/.
Exit codes: 64 — аргументы, 77 — нет --allow-sut, далее native pytest exit code.
versions.sh возвращает 69 при несовпадении описанной среды.

Allure raw results: allure-results/. Отчёт: allure-report/. Скриншоты/HTML: artifacts/.
Скрипты не удаляют старые результаты: перед анализом отделяйте результаты текущего
запуска от прежних, особенно статистику notify_telegram. Отчёт не отправляйте автоматически.
Указывайте команду, scope, версии, exit code, passed/failed/skipped и реальные артефакты.
Отдельно отмечайте collection без UI и setup errors; отсутствие выполненных тестов не PASS.
JUnit XML по умолчанию не настроен. [CI-контракт](../integrations/ci-github.md).
