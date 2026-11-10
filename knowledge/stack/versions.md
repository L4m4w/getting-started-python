# Версии

[requirements.txt](../../requirements.txt) — источник закреплённых зависимостей:
selenium 4.51.0, pytest 9.1.1, allure-pytest 2.16.2, python-dotenv 1.2.1.
Не обновляйте их до версий внешнего примера.

[Actions](../../.github/workflows/tests.yml): Python 3.13, Allure CLI 2.46.1.
[Jenkins](../../Jenkinsfile): label python-python314-jenkins-agent-1 (Python 3.14
по конфигурации и README), venv и remote Selenoid; фактическую версию подтвердите логом.
Версия Allure Jenkins tool задаётся администратором, Jenkinsfile её не закрепляет.

`sh tools/versions.sh actions|jenkins|local` проверяет Python major.minor и все
requirements через importlib.metadata. local допускает 3.13/3.14 как две описанные среды.
Другие версии не объявляются несовместимыми без проверки: это выход за описанную матрицу.
PYTHON задаёт путь интерпретатора. Скрипт не проверяет браузер, драйвер, сеть,
готовность стенда, Allure CLI или успешность интеграций.
