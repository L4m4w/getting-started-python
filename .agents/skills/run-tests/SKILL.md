---
name: run-tests
description: "Запускает выбранные существующие UI-тесты Niffler и сообщает подтверждённые результаты."
---

# run-tests

Следуйте [AGENTS.md](../../../AGENTS.md).

Прочитайте [команды](../../../knowledge/testing/run-tests.md) и
[окружение](../../../knowledge/architecture/test-data.md). Проверьте локальные изменения
и выберите минимальный scope из задания. Сверьте версии с целевой средой Actions/Jenkins.
Перед UI-прогоном проверьте collection и browser mode. Учитывайте разрешённый стенд,
remote-доступ и серверные записи регистрации; не запрашивайте повторно уже данное разрешение.
Используйте реальный node ID либо tools/run-tests.sh. Не вызывайте Telegram или CI как
побочный эффект локальной проверки. Сообщите команду, версии, exit code и counts;
разделите collection и выполненные UI-тесты. При падении используйте
[диагностику](../../../knowledge/testing/debugging.md).
