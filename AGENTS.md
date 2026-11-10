# Project Rules

UI-автотесты для niffler.qa.guru: Python 3.13 + pytest + Selenium,
Page Object, Allure.

## Запуск
- `pytest` — все тесты (chrome, headless по умолчанию)
- `pytest --browser=firefox`, `HEADLESS=false pytest`
- `BASE_URL=... AUTH_URL=... pytest` — переопределить стенд
- `pytest --alluredir=allure-results` → `allure generate allure-results -o allure-report --clean`

## Конвенции
- Тесты лежат в `tests/<область>/test_*.py`; Page Object в `pages/`,
  базовый класс `pages/base_page.py`
- В тестах нет прямых вызовов `driver` — только через page objects
- На методах page objects — `@allure.step`; проверки в тестах —
  `with allure.step(...)`
- Разметка тестов: `@allure.epic/.feature/.story/.severity/.title`
- Скриншот + page source на падении пишет conftest-хук в `artifacts/`
- Секреты — только env / GitHub Secrets / Jenkins Credentials,
  никогда в коде

## CI
- GitHub Actions: `.github/workflows/tests.yml` — паттерн
  "тесты с continue-on-error → отчёт и Telegram с if: always() →
  exit 1 в конце". Не нарушай этот порядок.
- Jenkins: `Jenkinsfile` — Allure-плагин + Telegram через credentials
- Уведомления: `notify_telegram.py` — всегда exit 0, без секретов skip


## Харнесс агента

Описание ниже относится к Niffler. Текущие исходники и конфигурация приоритетнее снимка документации.
Общайтесь на языке пользователя.

- [Архитектура и сценарии](knowledge/architecture/overview.md).
- [Жизненный цикл браузера и артефакты](knowledge/architecture/lifecycle.md).
- [Данные и окружение](knowledge/architecture/test-data.md).
- [Команды запуска](knowledge/testing/run-tests.md).
- [Проверки](knowledge/testing/assertions.md), [диагностика](knowledge/testing/debugging.md).
- [Версии](knowledge/stack/versions.md), [CI](knowledge/integrations/ci-github.md).
- Skills: [run-tests](.agents/skills/run-tests/SKILL.md),
  [create-ui-test](.agents/skills/create-ui-test/SKILL.md),
  [fix-failing-test](.agents/skills/fix-failing-test/SKILL.md).

Shell entry points запускаются явно через `sh tools/…`; это не MCP и не hooks.
Не меняйте стек, remote-конфигурацию или ожидаемые результаты ради зелёного прогона.
Учитывайте уже данную пользователем авторизацию. Просьба оценить файлы сама по себе
не означает запуск тестов, создание пользователей, отправку Telegram или запуск CI.
Если среда не готова, фиксируйте причину; не удаляйте возможности проекта для обхода проблемы.
В отчёте разделяйте статическую проверку, collection, UI-прогон и внешние интеграции.
