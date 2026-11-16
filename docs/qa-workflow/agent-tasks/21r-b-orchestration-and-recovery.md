# 21R-B — исправить orchestration и recovery

Ты — исполнитель 21R-B. Рабочая папка:
`/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Других агентов не запускай. Параллельные 21R-A/C имеют отдельные write
scopes. Прочитай AGENTS.md, `.agents/skills/run-tests/SKILL.md`,
[сводное решение 21](../handoffs/21-independent-workflow-review.md),
[wave 24](../handoffs/coordination-wave-24.md), handoff 21A/21B/21C,
runbook/каталог workflow и TestOps. Все обязательные уточнения сводного
решения имеют приоритет над предложенными исправлениями ревьюеров.

Исправь 21B F1–F6 и 21A F3/F4 в одном orchestration write scope:

1. `created` с сохранённым PR number не отправляет новый create при
   пустом поиске. Targeted get + exact spec/commit/tree могут подтвердить
   существующий ref; None/404/error/mismatch сохраняют blocked/unknown
   и старый номер. Даже доказанный 404 здесь не разрешает автоматически
   новый create. То же правило для re-prepare/revision/supersede.
2. Inherited intents пересверяются с доказуемо тем же parent workflow/
   intent/spec/result. Разрешение parent снимает ложный stale blocker,
   но не удаляет историю и не разрешает дубль старого remote effect.
   Exact ref усваивается только при текущих guards, несовместимость или
   missing/corrupt/ambiguous parent остаётся blocked. Не вводить
   обратный порядок locks/взаимную блокировку двух lineage; старый state
   читать, не модифицировать в обход его lock.
3. Reconcile с отсутствующим/невалидным spec и search exceptions в
   create/reconcile даёт controlled blocked/kept/unknown, без traceback
   и без перевода неизвестного эффекта в retry-safe. Не скрывать ошибки
   и не терять уже доказанные решения других intents при сбое позднего.
4. Corrupt TestOps state в verify/reconcile/observe — controlled 69,
   bytes повреждённого state неизменны, upload/run dispatch=0.
5. Base execution observation не перезаписывает head publication ни
   через verify, ни через reconcile; проверяй также fixture с уже
   подтверждённым head, чтобы не было деградации published из-за base.
6. После T8 повторный импорт прежнего base может удовлетворять strength
   только после полного актуального manifest/JUnit/source/scenario/
   provenance/environment check и доказанной эквивалентности. Привязать
   base к текущей ревизии с audit, не переписывая evidence и историю;
   повтор после успешной привязки — честный no-op. Head прошлой ревизии
   не переиспользовать; изменение sources/base/provenance блокирует.
   Не ослаблять execution_matches глобально и не расширять registry.
7. Implementation node IDs сопоставлять по boundary-token SID, чтобы
   UNIT-VAL-0010 не покрывал UNIT-VAL-001; сохранить реальные parametrized IDs.

Write scope строго:
- `infrastructure/workflow/orchestrator.py`;
- новый `tests/unit/test_workflow_21r_b.py`;
- новый `test_data/consts/workflow_21r_b.py` (данные только твоих тестов);
- `docs/qa-workflow/handoffs/21r-b-orchestration-and-recovery.md`;
- новый `artifacts/workflow-corrections/21r-b-<UTC>/`.

State/envelopes меняет A. Adapters/contracts/index/locks/CLI/shared
fixtures/constants/старые tests и общие docs не менять. Если ограничение
write scope реально мешает, зафиксируй конкретную зависимость; не правь
чужие файлы. Данные новых тестов — в собственном модуле констант выше,
с импортом в regression-файл. Каталог workflow единолично меняет C;
передай описания новых/изменённых public helpers и semantics в handoff.

Регрессии должны считать dispatch, а не только outcome. Created + empty
search + get None/error/mismatch: create остаётся 1; exact get: adoption,
create=1. Проверить app и tests. Unknown + changed revision: сначала
довести новую ревизию до executed, затем попытка create — blocked без
повтора; не засчитывать ранний фазный отказ на initialized. Supersede:
parent adopted → новая линия корректно понимает resolution; несовместимый
spec не публикуется. Добавь crash/ошибочные boundaries из пунктов выше.

Выполни новый regression-файл, `test_workflow_intents.py`,
`test_workflow_20r.py::TestF1UnresolvedExternalEffect`/`::TestF5RepeatAccept`,
`test_workflow_20r2.py::TestR4TestOpsCheckpoints`. Используй собственные
pytest basetemp/cache/JUnit/stores. Повтори B probes и C full-chain repeat
из копий с выводом только в новый evidence, read-only real compatibility.
Полный unit/collection и тесты A не дублируй без конкретной причины;
финальную проверку объединённого кода выполняет координатор.

Зафиксируй exact SHA inputs до/после относительно accepted manifest
`artifacts/workflow-implementation/coordinator-20r2-review-20261115/reviewed-inputs.sha256.json`.
Ожидаемые peer changes A в state/envelopes и C в docs отмечай отдельно;
не выдавай проверки разных версий за одну. 19 protected SHA из
`artifacts/workflow-implementation/20r2-20261115T195559Z/protected-sha-after.txt`
и 15 API sources manifest run-ni_5bvnc — неизменны до/после.

Все проверки offline на fake transports/runner/Git и isolated stores.
Никаких сети, API/UI/SUT, Docker/Gradle/CI, реальных TestOps/PR writes,
Git commit/push/checkout/reset. Приложение, рабочий workflow, accepted
execution state и исторические evidence/handoffs read-only. Секреты
не читать/копировать, все чужие изменения сохранить.
Handoff: ready/blocked, fixes→repro/regression, SHA, команды/exit/counts,
dispatch до/после, непроверенное и заметки для C. После отчёта остановись;
никакой отдельной приёмки 21R/MVP или разрешения Git/PR.
