---
name: create-ui-test
description: "Добавляет или расширяет UI-сценарии Niffler через существующие Page Objects."
---

# create-ui-test

Следуйте [AGENTS.md](../../../AGENTS.md).

Прочитайте [архитектуру](../../../knowledge/architecture/overview.md), ближайший тест,
соответствующий Page Object и [данные](../../../knowledge/architecture/test-data.md).
Переиспользуйте pages/; действия/локаторы остаются в Page Objects, проверки — в тестах
внутри allure.step. Сохраните epic/feature/story/severity/title по текущим примерам.
Проверяйте требования сценария; не фиксируйте количество assertions по примеру.
Не добавляйте direct driver calls, sleep, новые dependencies или второй объект той же страницы.
При добавлении case обновите selectors tools/run-tests.sh. Выполните статическую проверку
и collection, затем выбранный UI-тест в пределах разрешённого scope.
Отчёт должен различать написанный, собранный и реально выполненный тест.
