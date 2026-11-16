# 21R-A — исправить schema и envelopes

Ты — исполнитель 21R-A. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Работай самостоятельно, других агентов не запускай. Пользователь запускает
21R-B/C параллельно. Прочитай AGENTS.md, `.agents/skills/run-tests/SKILL.md`,
[сводное решение 21](../handoffs/21-independent-workflow-review.md),
[wave 24](../handoffs/coordination-wave-24.md), handoff 21A и актуальный
каталог `knowledge/components/workflow.md`.

Исправь только 21A F1/F2/F5:

1. Явно проверять типы/домены `expected_executions` и его элементов/
   `expect`, `strength_evidence`, execution `junit_summary`/`selection`
   и вложенные значения, которые используются в gate. Повреждённый
   state должен давать WorkflowSchema/StateCorruptError и CLI 69,
   без AttributeError/TypeError/traceback, до вычисления implied_phase.
   Проверять конкретные структуры, не маскировать все ошибки catch-all.
2. Для текущего фиксированного MVP требовать ровно обе PR роли app/tests
   и TestOps, `required is True` у всех. Missing/false/null/0/1/unknown
   role не дают published. Проверять и schema, и логический publication
   gate, чтобы direct gate тоже не принимал ослабленный набор.
   Не считать schema механизмом аутентификации произвольного state.
3. `True`/`False` запрещены как TestOps ID; int > 0 остаются валидными.

Write scope строго:
- `infrastructure/workflow/state.py`, `infrastructure/workflow/envelopes.py`;
- новый `tests/unit/test_workflow_21r_a.py`;
- новый `test_data/consts/workflow_21r_a.py` (данные только твоих тестов);
- `docs/qa-workflow/handoffs/21r-a-state-and-envelopes.md`;
- новый `artifacts/workflow-corrections/21r-a-<UTC>/`.

Orchestrator, shared fixtures/constants, старые tests/evidence и общие
документы не редактируй. Новые тестовые значения держи в собственном
модуле констант выше и импортируй его в регрессии, соблюдая AGENTS.md;
не создавай конкурирующие правки `test_data/consts/workflow.py`.
Новые shared helpers/API не нужны; если всё же необходимы — сначала
зафиксируй границу в handoff. Изменения существующего публичного API
согласуй с B/C сообщением через координатора; каталог единолично обновляет C.

Проверки: воспроизведи исходные failing cases из новых копий A probes,
добавь meaningful positive/negative regression, в том числе реальный
CLI subprocess на испорченной копии state с exit 69 и без изменения bytes.
Выполни свой новый regression-файл, `test_workflow_state.py::TestStateSchema`,
`::TestRevisionCascade` и `test_workflow_20r2.py::TestR2GitHeadSeparation`.
Все pytest basetemp/cache/JUnit и stores внутри своего evidence. Общий
unit/collection не повторяй: координатор проверит объединённую версию.

Baseline принятого кода — exact SHA в
`artifacts/workflow-implementation/coordinator-20r2-review-20261115/reviewed-inputs.sha256.json`.
Зафиксируй SHA своих inputs до/после и peer drift отдельно: B меняет
orchestrator, C — только два документа. Такое ожидаемое изменение не
является поводом переписать чужие файлы или объявить старую версию проверенной.
19 protected SHA из `artifacts/workflow-implementation/20r2-20261115T195559Z/protected-sha-after.txt`
и 15 API sources из manifest run-ni_5bvnc должны совпасть до/после.
Сохрани все чужие незакоммиченные изменения. Приложение read-only.

Никаких сети, API/UI/SUT, Docker/Gradle/CI, реальных TestOps/PR writes,
commit/push, переключения/reset checkout, чтения/копирования секретов.
Рабочий workflow, accepted execution state, исторические handoff/evidence
не менять. Отчёт: ready/blocked, точные SHA, fixes→tests/repro,
команды/exit/counts/evidence, ограничения и заметки C для каталога.
После handoff остановись: общая приёмка координатора после A/B/C.
