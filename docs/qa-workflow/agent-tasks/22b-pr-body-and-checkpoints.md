# 22B — durable PR body и checkpoint читаемого create number

Ты — исполнитель 22B. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
22A пишет HTTP transport параллельно, других агентов не запускай.
Прочитай AGENTS.md, локальный run-tests skill,
[общий контракт 22](22-github-pr-transport.md) как контекст,
[общий интерфейс](../design/22-pr-transport-interface.md),
[wave 28](../handoffs/coordination-wave-28.md), wave 26/27, handoff 21R2,
актуальные adapters/orchestrator. Общее поручение целиком не выполнять.

Твоя часть:
1. Воспроизводимый body_text + body_sha256 в spec/intent по закреплённому
   интерфейсу. Прочитать body bytes как UTF-8 без неявного trim/newline
   преобразования; новые absent/null/empty канонизировать None/None.
   Durable payload/input snapshot, проверка нужных source/snapshot
   digests перед dispatch; missing/drift blocked до POST. Legacy spec
   с hash без текста не угадывать и не переписывать автоматически.
2. Читаемый create ref number/URL сохранять до verification GET. Fault
   probes до/после каждого save/dispatch: не потерять известный remote
   effect и не вызвать второй create. Lost save до записи number оставляет
   dispatched/unknown blocking intent. После durable number — targeted get.
3. Сохранить idempotent prepare, frozen intent spec, safe re-prepare,
   unknown+[]/404 запреты, commit/tree/exact guards и 21R2 lineage.
   Использовать fake transports/runner/Git; HTTP/CLI wiring не твоя часть.

Write scope строго:
- `infrastructure/workflow/adapters.py`, `orchestrator.py`;
- новый `tests/unit/test_workflow_pr_payload.py`;
- новый `test_data/consts/workflow_pr_payload.py`;
- новый `docs/qa-workflow/design/22b-pr-body-and-checkpoints.md`;
- новый `docs/qa-workflow/handoffs/22b-pr-body-and-checkpoints.md`;
- новый `artifacts/workflow-github/22b-<UTC>/`.

Github.py/CLI, state/envelopes/contracts/index/locks, старые tests/fixtures/
consts, общий интерфейс и каталоги не менять. PrRef и search/create/get
сигнатуры сохранить, необходимые поля PrSpec расширить совместимо.
Если иначе невозможно — конкретный blocker координатору. Не ждать A:
fake transport по текущему протоколу достаточен для твоей части.
Изменения public API и semantics передать C в handoff; каталог обновит C.

Meaningful регрессии на app/tests: body отсутствует/пустой/nonempty/
CRLF/Unicode/невалидный UTF-8; digest/source/snapshot missing/drift;
legacy hash без payload; повтор prepare без новых эффектов; crash
после POST с читаемым номером перед verification; crash на save; get
failure; повтор create/reconcile/resume без нового dispatch; unknown +
[]; known +404/error; ancestry two-hop. Считать fake create/get/runner,
не только исход. Пути доводить до executed на корректных commit/tree.

Выполнить свой regression-файл, `test_workflow_intents.py`,
`test_workflow_21r_b.py`, `test_workflow_21r2.py`,
`test_workflow_20r2.py::TestR2GitHeadSeparation`, full-chain fake repeat
из новой копии в своём evidence. Не выполнять HTTP tests A/полный unit/
collection без причины. Свои basetemp/cache/JUnit/stores.

Сверить 19 protected SHA и 15 API sources manifest run-ni_5bvnc до/после;
зафиксировать exact inputs/outputs SHA относительно wave 26 и peer
дельты A отдельно. Никаких сети (для B docs не нужны), live PR/TestOps/
SUT/API/UI/Docker/Gradle/CI, Git commit/push/fetch/checkout/reset, установки
gh/deps, реальных tokens/.env. Все чужие изменения сохранить; рабочий
workflow, accepted execution state и исторические evidence read-only.
Handoff ready/blocked: SHA/design, commands/exit/counts/JUnit/evidence,
dispatch counters, API для C, ограничения. После отчёта остановись:
координатор принимает A/B перед зависимой C, весь 22/MVP не принимать.
