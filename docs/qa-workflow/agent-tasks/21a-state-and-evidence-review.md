# 21A — независимое ревью состояния и evidence contracts

Ты — независимый ревьюер 21A QA workflow Niffler. Работай параллельно с
21B/21C; других агентов не запускай. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.

Прочитай AGENTS.md, [общее поручение 21](21-independent-workflow-review.md)
как общий контракт (не выполняй его целиком), [wave 22](../handoffs/coordination-wave-22.md),
[разделение wave 23](../handoffs/coordination-wave-23.md), handoff/design
20R2, knowledge/components/workflow.md и runbook qa-workflow/TestOps.
20/20R2 уже приняты как offline-реализация; входы не требуют новой приёмки.

## Твоя часть

- `state.py`, `envelopes.py`, `contracts.py`: schema/gates, freshness,
  revision invalidation, dependency graph, source snapshot/копии/recheck,
  точный JUnit/raw Allure mapping, статусы/UUID/bindings/attachments,
  историческая baseline provenance. Связанные accept/import части
  orchestrator.py читай по необходимости.
- Независимые отрицательные probes: частичные/несогласованные inputs,
  corrupted state, stale review/implementation, missing/duplicate/foreign
  scenarios, чужой head/base, attempts обойти historical acceptance.
- Read-only compatibility run-ni_5bvnc и run-vzsatlfk: проверь реальную
  форму raw Allure, manifest/copies и происхождение данных. Это не новый
  API-прогон. Tree digests до/после должны совпасть.

Назначенные existing targeted tests (не дублируй полную группу):
`test_workflow_state.py::TestStateSchema`, `::TestRevisionCascade`,
`test_workflow_gates.py` целиком,
`test_workflow_20r2.py::TestR1SourceAndScenarioContract`,
`::TestR3HistoricalProvenance`.
Они не заменяют собственное ревью/пробы. Используй локальный run-tests skill.

Index/locks/concurrency, CLI и full-chain повтор — 21C;
PR/TestOps transport effects/checkpoints — 21B. Пересекающиеся вопросы
передай как finding со ссылкой на соответствующую часть, не расширяй
свою работу повторным полным аудитом. Чтение общих файлов разрешено.

## Изоляция и отчёт

Пишешь только `docs/qa-workflow/handoffs/21a-state-and-evidence-review.md`
и новый `artifacts/workflow-review/21a-<UTC>/` (свои probes/results/temp
stores). При direct pytest используй отдельные `--basetemp` и
`-o cache_dir=...` внутри своего evidence; stdout/JUnit тоже собственные.
Без правок source/tests/общих документов. Полный unit/collection не
повторяй без конкретной найденной причины.

До/после сверь accepted code SHA из coordinator-20r2 review,
19 protected SHA и 15 API files из 20R2 evidence. Остальные исполнители
параллельно создают свои отчёты: новые untracked docs/evidence не являются
source drift. При изменении принятых исходников зафиксируй точный blocker.

Никаких сети, SUT/API/UI, Docker/Gradle, CI, TestOps writes, commit/push/PR,
переключения/сброса checkout. Рабочий workflow и исторические evidence
read-only; секреты не читать/копировать. Все чужие изменения сохранить.

Handoff: ready/blocked/needs_decision, SHA версии, findings по приоритету
с file:line/trigger/consequences/repro, свои команды/exit codes/counts/
evidence, проверенное/непроверенное, рекомендации для Git/PR пакета.
Не исправляй findings и не принимай весь 21/MVP. После отчёта остановись;
координатор объединит 21A/21B/21C и выполнит общую приёмку.
