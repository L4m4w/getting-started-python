# CI и уведомления

## GitHub Actions

Источник: [tests.yml](../../.github/workflows/tests.yml).
Push в master, pull_request и workflow_dispatch с выбором chrome/firefox.
Python 3.13, локальный браузер; Selenium Manager разрешает driver.
Порядок: pytest с continue-on-error → отчёты/артефакты с always → Telegram →
exit 1 при failure тестового шага. Сохраняйте этот контракт.
Отчёт публикуется в gh-pages на push в master, результаты и failure artifacts архивируются.
Workflow содержит contents: write для публикации; не копируйте сюда TestOps-шаблон.

## Jenkins

Источник: [Jenkinsfile](../../Jenkinsfile).
Агент Python 3.14, venv, SELENIUM_REMOTE=true. Параметр Credentials выбирает
Selenoid username/password, withCredentials собирает remote URL внутри шага.
Сохраняйте credentials parameter: он нужен для user-scoped credentials.
Падение тестов даёт UNSTABLE через catchError; post always публикует Allure,
архивирует results и вызывает Telegram; unsuccessful архивирует artifacts, cleanup — cleanWs.
Конкурентные сборки запрещены, timeout 20 минут, история 20 билдов.

## Внешние операции

notify_telegram читает Allure JSON; без секретов уведомление пропускается.
Не запускайте его при обычной статической проверке.
Просмотр CI и его запуск — разные действия; повтор/dispatch, публикация и сообщения
требуют соответствующей задачи. tools/gh.sh — необязательная CLI-обёртка для GitHub,
GH_TOKEN и GITHUB_REPOSITORY задаются через разрешённое окружение.
Jenkins API helper не добавлен. Allure TestOps, Jira и Confluence в исходниках не настроены.
Файлы пайплайнов не подтверждают состояние внешних сервисов.
