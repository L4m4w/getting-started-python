# 21R2 — сохранить PR effect guard после разрешения parent lineage

Ты — исполнитель 21R2 QA workflow Niffler. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Других агентов не запускай. Прочитай AGENTS.md, локальный run-tests skill,
[приёмку wave 25](../handoffs/coordination-wave-25.md), handoff 21R-B,
сводное ревью 21, runbook/каталог. Исправляется **один связанный P1**,
не новая архитектура и не повтор всей 21R-A/B/C.

## Доказанный дефект и критерий

Повтори из новой копии пробу
`artifacts/workflow-corrections/coordinator-21r-review-20261116/inherited-zero-search.py`.
Она сохраняет данные рядом с копией; реальный workflow не используется.
На принятой к проверке версии parent adoption #42 → child executed →
search [] → create #101. Эта версия не принята для дальнейшего Git/PR.

Разрешение parent intent должно снимать ложный stale blocker, сохраняя
durable guard известного remote effect. Parent completed/adopted/created
не означает «записи не было». До любого нового dispatch учитывать
известный номер/spec/result в ancestry, а не только unfinished snapshots
и свежий search. Exact existing ref допускает adoption только после
текущих commit/tree/exact-spec guards; несовместимый ref, None/404,
ошибка/неполный поиск/[] сохраняют blocked/unknown без нового create.
Автоматический recreate по 404 не разрешён. Не удалять историю и не
переводить успешный create в failed/retryable для обхода guards.

Проверить также completed/created effect **до** supersede и второе
supersede (grandparent→parent→child): перенос только unfinished intents
не должен терять известный remote effect или unresolved ancestry.
Не полагаться на терминальность parent-state: старую линию допускается
reconcile, это уже используется текущими тестами. Parent читать без
обратного порядка locks; missing/corrupt/ambiguous history — fail-closed.

## Write scope

- `infrastructure/workflow/orchestrator.py`;
- новые `tests/unit/test_workflow_21r2.py`,
  `test_data/consts/workflow_21r2.py`;
- `knowledge/components/workflow.md`, `knowledge/components/consts.md`,
  `knowledge/integrations/qa-workflow.md` — только фактические изменения
  этого исправления и снятие remaining pending после своих проверок;
- новый `docs/qa-workflow/handoffs/21r2-pr-lineage-deduplication.md`;
- новый `artifacts/workflow-corrections/21r2-<UTC>/`.

State/envelopes/contracts/adapters/index/locks/CLI, старые tests/fixtures/
consts, исторические handoffs/evidence read-only. При реальной нужде
расширения source scope зафиксировать конкретный blocker, не править
чужие файлы. Сохранять все незакоммиченные изменения.

## Проверки

Регрессии на обе роли app/tests, на корректных commit/tree fixtures,
с child уже executed. Считать реальный fake create до/после, не только
outcome. Parent unknown→adopted→child + []/get None/error/mismatch:
create counter не увеличивается. Exact compatible ref — adoption или
честный blocked, без ложного verified чужого дерева. Повторы
prepare/create/reconcile/resume/revision/supersede, completed/created
до supersede и two-hop ancestry должны сохранять guard и историю.
Контроль: первый действительно новый create без прежнего effect
остаётся рабочим. Не засчитывать фазный отказ initialized как проверку.

Выполни новый regression-файл и `test_workflow_21r_b.py`,
`test_workflow_intents.py`,
`test_workflow_20r.py::TestF1UnresolvedExternalEffect`,
`test_workflow_20r2.py::TestR2GitHeadSeparation`.
Повтори full-chain fake repeat и новую координаторскую пробу из копий
с выводом в собственное evidence. Basetemp/cache/JUnit/stores раздельные.
Общий unit/collection без конкретной причины не повторять.

Exact стартовая версия:
`artifacts/workflow-corrections/coordinator-21r-review-20261116/reviewed-inputs.sha256.json`.
Зафиксировать before/after code/docs SHA. 19 protected SHA из
`artifacts/workflow-implementation/20r2-20261115T195559Z/protected-sha-after.txt`
и 15 API sources manifest run-ni_5bvnc неизменны. A/C и исправленные
пути B не деградируют. Каталог должен описывать реальные API/семантику,
а не обещанный будущий эффект.

Только offline fake runner/transport/Git и isolated stores. Никаких
сети/SUT/API/UI, Docker/Gradle/CI, live TestOps/PR writes, commit/push,
переключения/reset checkout, чтения/копирования секретов. Рабочий
workflow, accepted execution state и приложение read-only; исходники
старого evidence не запускать на месте и не переписывать.
Handoff: ready/blocked, exact SHA, root cause и решение, команды/exit/
counts/JUnit/evidence, dispatch counters, сохранённые ограничения.
После отчёта остановиться: общая приёмка и актуализация 19A — координатору.
