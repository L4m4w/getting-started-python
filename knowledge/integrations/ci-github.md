# GitHub Actions: чтение и запуск

Источник конфигурации — `.github/workflows/tests.yml`.
`tools/gh.sh` использует установленный `gh`, существующую авторизацию gh
или `GH_TOKEN`, и явный `GITHUB_REPOSITORY=owner/repo`.
Не сохраняй токен в документацию, не запускай интерактивный login от имени агента.

```sh
GITHUB_REPOSITORY=L4m4w/getting-started-python sh tools/gh.sh runs
GITHUB_REPOSITORY=L4m4w/getting-started-python sh tools/gh.sh view 123
GITHUB_REPOSITORY=L4m4w/getting-started-python sh tools/gh.sh view-log 123
```

При расследовании CI-only ошибки сначала прочитай лог нужного запуска.
Наличие workflow не доказывает успешный прогон или работоспособность секретов.

## Поведение по событиям (`tests.yml`)

- `pull_request`: только offline unit-тесты — явная выборка `pytest tests/unit`,
  без обращения к публичному SUT. Креды `EXISTING_USERNAME`/`EXISTING_PASSWORD`
  и `BASE_URL`/`AUTH_URL` в тестовый шаг не передаются. Telegram-уведомление
  и восстановление истории Allure из gh-pages (`git fetch`) не выполняются.
  Деплой в gh-pages и так привязан к push master. Allure results/report
  продолжают загружаться как artifacts; падение unit-тестов даёт красный job
  (тот же паттерн `continue-on-error` → отчёт → `exit 1`).
- `push` в `master` и `workflow_dispatch`: прежнее поведение — полный прогон
  `pytest` (UI-тесты против `BASE_URL`/`AUTH_URL` с секретами), восстановление
  истории, деплой отчёта в gh-pages на master, Telegram-уведомление.
  Их UI/SUT effects сохраняются без изменений.
- API runtime (`tests/api`), его секреты `API_*` и стенд в CI не подключены.

Следующие команды выполняются только при имеющемся разрешении на CI-запуск:

```sh
GITHUB_REPOSITORY=L4m4w/getting-started-python sh tools/gh.sh --allow-ci-write rerun 123
GITHUB_REPOSITORY=L4m4w/getting-started-python sh tools/gh.sh --allow-ci-write dispatch firefox
```

Dispatch запускает `tests.yml`, передаёт существующий input `browser`
(`chrome` по умолчанию). Rerun повторяет исходный запуск целиком и может снова
создать тестовых пользователей. Оба действия используют сеть и CI-ресурсы;
флаг не заменяет разрешение. Локальная проверка harness не запускает эти команды.

Jenkins остаётся отдельной интеграцией из `Jenkinsfile` и README.
TestOps подготовлен отдельным локальным CLI: [runbook](testops.md).
Автоматическая загрузка в GitHub Actions/Jenkins не подключалась.
