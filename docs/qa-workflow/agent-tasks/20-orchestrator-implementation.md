# 20 — минимальный оркестратор и offline-проверки

Ты — исполнитель 20 QA workflow Niffler. Реализуй минимальный оркестратор
после принятого этапа 19. Других агентов не запускай.

Рабочая папка: `/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Приложение: `/Users/zenalark/PycharmProjects/Test-java/niffler-py-st3` (read-only).

## Принятые входы

Прочитай AGENTS.md, каталог knowledge/components и применимые разделы,
docs/plans/qa-workflow-mvp.md,
docs/qa-workflow/design/19-orchestrator-contract.md,
docs/qa-workflow/handoffs/19a-git-pr-preparation.md,
docs/qa-workflow/handoffs/19b-orchestrator-contract.md,
docs/qa-workflow/handoffs/coordination-wave-17.md и
**docs/qa-workflow/handoffs/coordination-wave-19.md целиком**.
Wave 19 — документированная приёмка и обязательные уточнения контракта;
при противоречии с предложением 19B применяй wave 19. Повторной приёмки
для начала разрешённой локальной реализации не требуется.

Изучи tools/harness.py, tools/testops.py, существующие state/lifecycle/
results/verification helpers и knowledge/integrations/testops.md.
API/TestOps 16–18 завершены; это не новая публикация и не новый API-прогон.

## Область записи

- `infrastructure/workflow/` — schema/state/index/locks, gates, intents,
  orchestrator и adapters; число модулей выбирай по ответственности.
- `tools/workflow.py`, `tools/run-workflow.sh`.
- `tests/unit/test_workflow*.py`, `test_data/consts/workflow.py` и при
  необходимости строго связанные `test_data/utils/workflow*.py`.
- `knowledge/components/README.md`, `infrastructure.md`, `consts.md` и
  новый `workflow.md` при вынесении большого раздела; документируй каждый
  новый общий компонент/публичный интерфейс в том же изменении.
- `knowledge/integrations/qa-workflow.md` — CLI/runbook и ограничения.
- `docs/qa-workflow/design/20-orchestrator-implementation.md` — актуальная
  схема/уточнения реализации и валидные/невалидные JSON fixtures/examples.
- `docs/qa-workflow/handoffs/20-orchestrator-implementation.md`.
- Новый `artifacts/workflow/` state и уникальный
  `artifacts/workflow-implementation/20-<UTC>/`; unit fixtures в temp dirs.
  Новые unit evidence harness создаётся штатным wrapper.

Общие workflow README/индекс поручений/план MVP и исторические handoffs,
evidence 19B и production/API/TestOps исходники не редактируй.
Не меняй зависимости ради удобства; используй доступные библиотеки/stdlib.
Если подтверждённый дефект существующего публичного контракта мешает
реализации, укажи точный блокер и минимальную предлагаемую правку, не
подменяй scope незаметным изменением guards.

## Результат

1. Рабочий CLI init/status/accept/check/run-execution/import-execution/
   resume/doctor/reconcile, локальный PR spec и интерфейс PR transport.
   Можно разумно объединять подкоманды, документируя соответствие 19B.
   Произвольные shell-команды из входных артефактов не исполнять;
   subprocess — фиксированный allowlist, argv без shell=True.
2. Строгая versioned validation всех accepted inputs и собственного state,
   canonical digests и явный snapshot scope. JSON envelope связывает
   Markdown с ID/coverage/review/node IDs. Проверять содержимое/источники,
   dependency graph, phase gates; не принимать «статус approved» без
   версии и совпадающего digest сценариев. Корректные examples создавай
   заново, не используя заглушки state-valid.json 19B как accepted state.
3. Index/revision/state с одним писателем и crash-safe сохранением.
   Соблюдай wave 19 по index lock, межфайловому восстановлению,
   порядку locks и наследованию незавершённых intents при supersede.
   Коррупция/неизвестная схема блокирует операцию без перезаписи.
4. Реальное делегирование compile/collection и harness/TestOps через
   существующие CLI, с внедряемым runner для offline-проверок. Раздели
   run API, unit checks и их результаты: unit не удовлетворяет gate
   API head=6 passed. Resume не повторяет completed этапы и не делает
   blind retry unknown run/upload/PR. Execution intent связан с конкретным
   evidence, а не с последним найденным run каталогом.
5. TestOps execution state — единственный источник статуса отправки.
   guards/integrity сохраняются; собственный кэш не разрешает resend.
   Не импортируй конкретный исторический execution как текущее выполненное
   действие без проверки. Source=imported явно, provenance и SHA сохраняются.
   Чтение accepted uploaded execution не должно запускать plan/package/
   assign/upload/verify save над ним. Bindings уже согласованы.
6. PR transport в 20 — протокол и fake, live create/push недоступны.
   Fake end-to-end тесты реализуют intents/search/get/adopt для app и QA;
   unknown + zero search остаётся blocked, а не retry-safe. Реальный
   published не выставляется по fake или одному launch.
7. Каталог компонентов, runbook с воспроизводимыми offline командами,
   схема состояния, пределы автоматизации и перечень непроверенного.
   Human/LLM этапы принимаются программно как проверяемые артефакты;
   не нужен собственный LLM runtime или универсальный scheduler.

## Обязательная проверка

Реализуй meaningful offline tests M1–M18 из 19B с поправками wave 19:
- повтор одного входа, conflict/supersede и отсутствие обхода guards;
- новый app head/dirty source/requirements/env/bindings и stale gates;
- повтор после сбоя/прерывания на durable boundaries каждого этапа;
- реальная конкурентная запись index/state и отказ второму писателю;
- crash между index/state updates и до/после intent dispatch/save;
- fake upload success до workflow save, повтор не отправляет upload;
- fake PR create success до save → один create и adopt; unknown+zero,
  incomplete/foreign/mismatch/multiple search → блок;
- неопределённый harness execution не запускается повторно;
- строгая validation, corrupt/unsupported state неизменён после отказа;
- skipped phase/review digest mismatch и fake checks не проходят gates;
- read-only import accepted execution: state/log/package SHA неизменны;
- separate new execution не подменяет старый; TestOps failure не вызывает
  run API/генерацию, terminal repeat не вызывает transport.

Не своди тесты к проверке собственной сериализации: проверяй наблюдаемое
поведение CLI, subprocess dispatch counts, файловую неизменность,
восстановление и конкурентность. Fake transports и executions держи в
temp dirs; не используй рабочие uploaded states как мутируемые fixtures.
При offline демонстрации full chain явно маркируй fake данные и результат.

Используй локальный skill `.agents/skills/run-tests/SKILL.md` для запусков.
Выполни подходящие targeted проверки, затем штатные compile/collection
и unit group; не повторяй их без новых изменений/ошибок. Сохрани команды,
exit codes, количества и evidence. Проверь git diff --check и локальные
Markdown-ссылки новых документов. Перед/после зафиксируй SHA исторических
state/log run-ni_5bvnc и старых принятых state, подтверждая неизменность.

## Ограничения и handoff

Не запускай API/UI/SUT, Docker/Gradle, CI, сеть, TestOps write, Git
commit/push/PR. Флаги execute/online сами не являются новым разрешением.
Не читай/копируй секреты, не переключай/сбрасывай общий checkout,
сохрани чужие незакоммиченные изменения. Принятые файлы приложения и
API-контракт не меняются; старые публикации не повторяются.

Handoff: ready/blocked/needs_decision, версии/SHA входов, изменённые файлы,
решения по контракту, команды/exit codes/числа, evidence, доказанное и
непроверенное. Отдельно перечисли ограничения будущего live PR workflow
и влияние на актуализацию пакета 19A. Не объявляй весь MVP завершённым.
После handoff остановись: координатор принимает 20 перед поручением 21.
