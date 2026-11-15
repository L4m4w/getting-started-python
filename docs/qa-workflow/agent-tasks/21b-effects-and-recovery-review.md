# 21B — независимое ревью внешних эффектов и восстановления

Ты — независимый ревьюер 21B QA workflow Niffler. Работай параллельно с
21A/21C; других агентов не запускай. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.

Прочитай AGENTS.md, [общее поручение 21](21-independent-workflow-review.md)
как общий контракт (не выполняй его целиком), [wave 22](../handoffs/coordination-wave-22.md),
[разделение wave 23](../handoffs/coordination-wave-23.md), handoff/design
20R2, knowledge/components/workflow.md и runbook qa-workflow/TestOps.
20/20R2 уже приняты как offline-реализация; входы не требуют новой приёмки.

## Твоя часть

- Effect/recovery части orchestrator.py и adapters.py: run/upload/verify/
  PR intents, unknown reconciliation, snapshots spec, inherited intents,
  supersede/revision, local TestOps plan/assign/package checkpoints.
- PR: настоящий Git commit/tree отдельно от patch/dirty snapshot,
  проверки exact spec/head/body/files, частичный/пустой/неоднозначный
  search. Положительный fake path — на commit/tree fixture, а не patch.
- Независимые fault probes до/после persisted intent и после успеха
  fake subprocess до save. Считай реальные fake dispatch: unknown PR
  + zero search + changed spec/revision/supersede не повторяет create;
  sent/inconclusive/unknown не повторяет upload/pytest; prepare после
  каждой crash boundary восстанавливается без повторного готового шага.
- Транспорт TestOps использует существующий state/guards; прочитай
  нужные helpers, но не запускай реальные внешние операции.

Назначенные existing targeted tests:
`test_workflow_intents.py` целиком,
`test_workflow_20r.py::TestF1UnresolvedExternalEffect`,
`::TestF4VariantClassification`,
`test_workflow_20r2.py::TestR2GitHeadSeparation`,
`::TestR4TestOpsCheckpoints`.
Используй локальный run-tests skill; не ограничивайся тестами автора.

Schema/source/scenario/provenance contracts — 21A;
index/locks/CLI/full-chain integration repeat — 21C. Общие файлы можно
читать; findings на стыке пометь для координатора, без повторного полного
аудита чужой части. Общую production реализацию не изменяй.

## Изоляция и отчёт

Пишешь только `docs/qa-workflow/handoffs/21b-effects-and-recovery-review.md`
и новый `artifacts/workflow-review/21b-<UTC>/` (свои scripts/results/
isolated stores). Direct pytest: собственные `--basetemp`,
`-o cache_dir=...`, stdout/JUnit внутри своего evidence. Полный unit/
collection не повторять без конкретной найденной причины.

До/после сверь accepted code SHA из coordinator-20r2 review,
19 protected SHA и 15 API files из 20R2 evidence. Новые docs/evidence
21A/21C не являются source drift. При изменении принятых исходников
зафиксируй точный blocker, не подменяй проверенную версию.

Никаких сети, SUT/API/UI, Docker/Gradle, CI, live TestOps/PR, commit/push,
новых агентов или переключения/сброса checkout. Рабочий workflow и
исторические state/evidence read-only. Секреты не читать/копировать;
все чужие изменения сохранить. Проверки только fake transports/temp dirs.

Handoff: ready/blocked/needs_decision, SHA версии, findings по приоритету
с file:line/trigger/consequences/repro, свои команды/exit codes/counts/
evidence, проверенное/непроверенное, ограничения live transport и
рекомендации для Git/PR пакета. Findings не исправляй. Не принимай весь
21/MVP; после отчёта остановись для объединённой приёмки координатором.
