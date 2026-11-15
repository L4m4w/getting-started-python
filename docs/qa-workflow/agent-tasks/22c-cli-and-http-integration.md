# 22C — CLI wiring и интеграция GitHub transport

**Входы A/B приняты, запуск разрешён:**
[wave 30](../handoffs/coordination-wave-30.md).
Exact baseline:
`artifacts/workflow-github/coordinator-22ar-review-20261116/accepted-inputs.sha256.json`.
Использовать исправленную A после 22AR; B неизменна. Существующий CLI
флаг `--body` уже передаёт body_path — сохранять его. В get учитывать
detail → files → повторный detail и changed_files equality; оба P1
wave 29 исправлены. Следующее условие приёмки уже выполнено wave 30.

**Зависимая задача: не запускать до документированной приёмки 22A и 22B
координатором.** Наличие двух ready handoff само по себе не равно приёмке.
Пользователь получит отдельный сигнал на запуск. Это не третья одновременно
стартующая часть.

Ты — исполнитель 22C. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Других агентов не запускай. Прочитай AGENTS.md, локальный run-tests skill,
общее поручение 22, [общий интерфейс](../design/22-pr-transport-interface.md),
wave 28, handoff/design A/B и новое решение координатора об их приёмке
с exact SHA. Если решения ещё нет — не выполнять зависимые правки.

Реализовать глобальный `--pr-transport {none,github}` default none,
lazy import/constructor transport и wiring app/tests в Orchestrator.
Сеть только --online, POST только --execute + --online + действующие
guards. Без флагов и в status/init/doctor/prepare — ноль credential
reads/HTTP. Не делать network healthcheck ради выбранного transport.

Write scope:
- `tools/workflow.py`;
- новый `tests/unit/test_workflow_github_cli.py`;
- новый `test_data/consts/workflow_github_cli.py`;
- `knowledge/components/workflow.md`, `knowledge/components/consts.md`,
  `knowledge/integrations/qa-workflow.md` (A/B API тоже интегрировать);
- новый `docs/qa-workflow/design/22c-cli-and-http-integration.md`;
- новый `docs/qa-workflow/handoffs/22c-cli-and-http-integration.md`;
- новый `artifacts/workflow-github/22c-<UTC>/`.

Github.py/adapters/orchestrator и A/B tests/consts read-only: реальные
стыковые дефекты передать координатору, не маскировать в CLI и не менять
протокол. Сводные handoff 22, README/plans и финальная приёмка — координатора.

Реальные CLI subprocess smoke с fake HTTP injection/bootstrap без выхода
в сеть: parser/global flag порядок; default none; missing --online/execute/
credential => zero HTTP; ранние команды zero HTTP/credential reads;
достижимый create с temp fixture и fake commit/tree; HTTP GET/POST
counters. Использовать настоящий GitHubPrTransport A и body/checkpoints B,
а не заменить оба компонента stub-результатом. Test-only injection не
превращать в production arbitrary endpoint/disable-guards флаг.
Разделять subprocess CLI и programmatic integration в отчёте.

Повторить после wiring: новый CLI regression-файл, HTTP tests A,
payload tests B, full-chain fake repeat, unknown+[]/known404 и crash
на читаемом number с нулём новых POST. Existing workflow regressions
A/B уже выполнили; без новой причины все повторно не гонять. Свои
basetemp/cache/JUnit/stores. docs/API/exit codes сверить фактически.

Перед/после exact SHA принятой A/B версии, 19 protected SHA и 15 API
sources run-ni_5bvnc. Никаких реальных GitHub API/PR/TestOps/SUT/API/UI/
Docker/Gradle/CI, Git commit/push/fetch/checkout/reset, установки gh/deps,
реальных tokens/.env. Исторические state/evidence, рабочий workflow и
чужие изменения сохранить. Сеть не нужна (официальные источники A уже
в design); непроверенное live явно отметить.
Handoff ready/blocked с SHA, commands/exit/counts/evidence, counters,
каталогом API и ограничениями. После него координатор проверяет весь 22,
обновляет QA-пакет и готовит отдельное разрешение Git/PR. Offline ready
не означает live verified и не завершает MVP.
