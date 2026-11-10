# Харнесс Niffler

Харнесс встроен в getting-started-python. Исходники и конфигурация проекта
приоритетнее описания. Начните с [AGENTS.md](AGENTS.md) и
[карты архитектуры](knowledge/architecture/overview.md).

- knowledge/ — архитектура, данные, окружение, диагностика и CI.
- .agents/skills/ — запуск, создание и исправление UI-тестов.
- tools/ — явные shell-команды проверки и запуска; не MCP и не hooks.

Текущий набор: девять UI-сценариев, Page Object, Chrome/Firefox,
локальный и remote WebDriver, Python 3.13 в Actions и 3.14 в Jenkins.
Команды выполняются из корня проекта; PYTHON позволяет выбрать интерпретатор.
[Подробнее о запуске](knowledge/testing/run-tests.md).

Наличие skills не подтверждает их обнаружение конкретным агентом.
Статическая проверка не подтверждает работу браузера или внешнего CI.
Allure TestOps не настроен.
