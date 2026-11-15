# 21R-C — runbook и каталог workflow

Ты — исполнитель 21R-C. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Других агентов не запускай. Прочитай AGENTS.md,
[сводное решение 21](../handoffs/21-independent-workflow-review.md),
[wave 24](../handoffs/coordination-wave-24.md), handoff 21C и текущие
runbook/каталог workflow. A/B параллельно исправляют код; ты единственный
редактор двух общих документов ниже.

Write scope строго:
- `knowledge/integrations/qa-workflow.md`;
- `knowledge/components/workflow.md`;
- `docs/qa-workflow/handoffs/21r-c-runbook-and-catalogue.md`;
- новый `artifacts/workflow-corrections/21r-c-<UTC>/`.

Исправь 21C F1: задокументируй глобальные `--store-dir`/`--workflow-id`
до subcommand и конкретные команды status/doctor/resume/accept/PR для
store с несколькими линиями после supersede. Не обещай автоматический
выбор active workflow: сейчас нужен явный ID. Закрепи интерпретатор
`PYTHON=.venv/bin/python` для будущего 19A; уточни, что check запускает
compile/list, а doctor не является полным реальным прохождением цепочки.

Исправь каталог: `drive_commit_to_executed` — метод Project, не
модульная функция. Уточни наблюдение verify timestamps и стабильные
identity digests при повторе; fake published отделяй от live/MVP.
Reconcile может записывать локальный state — read-only относится к
внешнему remote effect, не к собственному хранилищу.

Документируй обязательные решения 21R: обе PR роли/TestOps обязательны,
created/unknown не разрешают retry по пустому search/404, inherited
resolution требует проверяемого parent evidence, безопасный base rebind
после T8 требует полной повторной валидации. Пока A/B handoff отсутствуют,
явно отмечай эти разделы как целевой контракт 21R с pending verification;
не описывай ожидаемые исправления как уже проверенный код. Сверь готовые
handoff A/B, если появились к окончанию, и укажи SHA прочитанной версии.
Если нет — перечисли точные пункты для финальной сверки координатором;
это не блокирует документационную часть и не требует ждать агентов.

Не меняй README/plans/старые handoffs, реализацию, тесты, shared
fixtures/constants и чужое evidence. Не запускай полный unit/collection:
достаточно проверки локальных Markdown-ссылок, соответствия parser/API
read-only и diff --check. Зафиксируй исходные/итоговые SHA двух документов
и прочитанных code inputs, различай peer drift A/B и проверенную версию.

Никаких сети, SUT/API/UI, Docker/Gradle/CI, реальных TestOps/PR writes,
commit/push/checkout/reset, чтения/копирования секретов. Рабочий workflow,
accepted execution state и приложение read-only. Сохрани все чужие
незакоммиченные изменения. Handoff: ready/blocked, изменения, команды/
exit/evidence, pending API/semantics сверки и точные ограничения 19A.
После отчёта остановись: общая приёмка координатора ждёт A/B/C.
