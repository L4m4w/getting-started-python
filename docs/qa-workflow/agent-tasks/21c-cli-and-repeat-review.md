# 21C — независимая интеграционная проверка CLI и повтора workflow

Ты — независимый ревьюер 21C QA workflow Niffler. Работай параллельно с
21A/21B; других агентов не запускай. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.

Прочитай AGENTS.md, [общее поручение 21](21-independent-workflow-review.md)
как общий контракт (не выполняй его целиком), [wave 22](../handoffs/coordination-wave-22.md),
[разделение wave 23](../handoffs/coordination-wave-23.md), handoff/design
20R2, knowledge/components/workflow.md и runbook qa-workflow/TestOps.
Принятие 20/20R2 уже есть; не жди отчётов 21A/21B для своей проверки.

## Твоя часть

- CLI tools/workflow.py/run-workflow.sh, index.py/locks.py и orchestration
  границы: selection lineage, порядок locks, concurrent writers,
  межфайловая durability index/state, процесс/exit codes и документация.
- Повтори весь фиксированный fake workflow в своём isolated store:
  init → envelopes context/scenarios/review/implementation/bindings →
  base/head → TestOps prepare/upload/verify → два PR. Затем повтори тот
  же вход и выполненные шаги; сравни lineage/execution/package/PR
  identity и dispatch counters до/после, а не только printed status.
  Human/LLM inputs — явные envelopes; PR happy path — отдельный
  commit/tree fixture. Fake published маркируй simulation. Реальный
  patch/dirty пилот должен оставаться pending, без live create.
- Реальный CLI subprocess smoke в отдельном --store-dir:
  init/status/doctor/resume/repeated init на read-only repo facts.
  Это отдельно от проверки programmatic API с fake runner. Не выполняй
  API dispatch и не делай Git commits для fixture; используй имеющуюся
  fake Git модель для программных тестов.
- Конкуренция/восстановление index/state, изоляция двух независимых
  lineage и отказ второму писателю. Проверь, что факт new untracked
  отчётов соседних ревьюеров не вызывает ложный drift API source scope.
- Сопоставь documented commands/capabilities/exit codes с фактическим CLI,
  catalogue — с публичными API; выпиши ограничения для будущего пакета 19A.

Назначенные existing targeted tests:
`test_workflow_orchestrator.py` целиком,
`test_workflow_state.py::TestIndex`,
`test_workflow_20r.py::TestF5RepeatAccept`.
Локальный run-tests skill обязателен для запусков; добавь свои probes
в своей evidence области, существующие тесты не редактируй.

Глубокий source/scenario/provenance audit — 21A; отдельные effect crash
matrices и PR/tree verification — 21B. Проверка их интеграции в full-chain
repeat — твоя ответственность, это не зависимость от их отчётов.
Если готовый repeat падает, локализуй и сообщи trigger; не исправляй код.

## Изоляция и отчёт

Пишешь только `docs/qa-workflow/handoffs/21c-cli-and-repeat-review.md`
и новый `artifacts/workflow-review/21c-<UTC>/`. Все CLI --store-dir,
fake stores, --basetemp, cache_dir, stdout/JUnit — только собственные.
Не используй рабочий artifacts/workflow даже как smoke target записи.
Полный unit/collection не повторять без конкретной найденной причины.

До/после сверь accepted code SHA из coordinator-20r2 review,
19 protected SHA и 15 API files из 20R2 evidence. Общие code/docs не
редактируй; новые docs/evidence 21A/21B не являются source drift.
При drift исходников укажи точную версию и blocker.

Никаких сети, SUT/API/UI, Docker/Gradle, CI, TestOps writes, live PR,
commit/push, новых агентов или переключения/сброса checkout. Исторические
evidence/state read-only, секреты не читать/копировать, все чужие
незакоммиченные изменения сохранить.

Handoff: ready/blocked/needs_decision, SHA версии, findings с приоритетом/
file:line/trigger/consequences/repro, свои команды/exit codes/counts/
evidence, таблица повторённых шагов и dispatch до/после, отдельно CLI
subprocess vs programmatic simulation, проверенное/непроверенное.
Не принимай весь 21/MVP. Остановись после отчёта: координатор объединит
21A/21B/21C, проверит стыки и оформит общую приёмку.
