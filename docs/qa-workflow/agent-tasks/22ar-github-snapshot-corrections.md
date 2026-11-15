# 22AR — полнота и согласованность GitHub PR snapshot

Ты — исполнитель 22AR. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Других агентов не запускай. Прочитай AGENTS.md, локальный run-tests skill,
[wave 29](../handoffs/coordination-wave-29.md), handoff/design 22A,
[общий интерфейс](../design/22-pr-transport-interface.md), реализацию A.
22B принят, C ждёт приёмки исправленной A. Это два конкретных P1, не
повтор всего 22 и не новая архитектура.

Воспроизвести из новых копий
`artifacts/workflow-github/coordinator-22ab-review-20261116/github-probes.py`
и `github-integration-probes-v2.py`. Они сохраняют результаты рядом с
копией и используют отдельные stores относительно неё. Исторические
scripts/results на месте не запускать. Сейчас negative incomplete-files
и head-race ошибочно возвращают exact/verified; control должен работать.

## Исправления

1. `get` должен доказывать полноту files: валидный changed_files count
   PR detail (int>=0, без bool), полный уникальный список из endpoint,
   точное равенство количества. Missing/invalid/contradictory count,
   partial pagination, truncation/документированный server limit —
   controlled failure, не ref, принятый за полный. Сам факт отсутствия
   Link не отменяет известное count-противоречие.
2. Detail → все files pages → повторный detail, с проверкой неизменности
   использованных полей (PR number/repo/head SHA/base SHA/branches/
   title/body/draft/state/merged/count). Drift/неполный или ошибочный
   повторный ответ => controlled failure, без ложного verified. Никаких
   бесконечных retry и повторных POST. Граница утверждения — согласованный
   наблюдаемый снимок, не атомарная блокировка сервера.
3. Сохранить create: один POST, ноль verification GET до возврата
   читаемого number. Новые reads добавляются только в `get`, после
   checkpoint B. 404/unknown/lineage guards не ослаблять. search не
   превращает conflicting candidates в пустой список.

Write scope:
- `infrastructure/workflow/github.py`;
- `tests/unit/test_workflow_github.py`,
  `test_data/consts/workflow_github.py` — обновить реалистичные PR fixtures
  обязательным count, сохранить старые отрицательные сценарии;
- новые `tests/unit/test_workflow_github_snapshot.py`,
  `test_data/consts/workflow_github_snapshot.py` при необходимости;
- новый `docs/qa-workflow/design/22ar-github-snapshot-corrections.md`;
- новый `docs/qa-workflow/handoffs/22ar-github-snapshot-corrections.md`;
- новый `artifacts/workflow-github/22ar-<UTC>/`.

Adapters/orchestrator/CLI/state/contracts, B tests/consts, общий интерфейс,
старые handoffs/design/evidence, пакеты19A2 и каталоги read-only. API
сигнатуры A/B сохраняются. Новые snapshot semantics передать C через
handoff; общий каталог обновит C. При нужде расширить scope — конкретный
blocker координатору, не самостоятельная правка принятых B файлов.

Регрессии: matching/zero count; missing/negative/bool count; mismatch
files<count и files>count; несколько страниц/пропуск/дубликаты/лимит;
изменения head/base/title/body/status/count во время pages; failure/404
финального GET. Положительный стабильный get возвращает exact ref,
inconsistent get не даёт orchestrator verified. Проверить обе роли
app/tests через настоящий transport A и принятую B, fake HTTP/Git/runner.
В сценарии с выполненным create номер остаётся записанным, повторный
POST=0 даже при ошибке get. Считать вызовы HTTP, а не только outcomes.

Выполнить HTTP tests A + новый regression, payload tests B (не менять),
координаторские probes из копий. Общий unit/collection и все прежние
96 regressions без конкретной причины не повторять. Свои stores/
basetemp/cache/JUnit/evidence. Exact baseline — reviewed-inputs manifest
`artifacts/workflow-github/coordinator-22ab-review-20261116/` (A ещё не
принят, B принят). 19 protected SHA и 15 API sources run-ni_5bvnc
неизменны до/после. Сохранить все чужие изменения.

Только offline fake HTTP. При необходимости уточнить схемы допускается
публичная официальная docs.github.com, как в 22A, с URL/датой в новом
design. Реальные repository/API/PR/TestOps/SUT/UI/Docker/CI/Git writes,
tokens/.env/установка gh/deps запрещены. Рабочий workflow, accepted
execution state и исторические evidence read-only.
Handoff ready/blocked: root cause, exact SHA, commands/exit/counts/JUnit,
probes/HTTP counters, границы live. После отчёта остановиться:
координатор принимает A/B до запуска C; весь 22/MVP не принимать.
