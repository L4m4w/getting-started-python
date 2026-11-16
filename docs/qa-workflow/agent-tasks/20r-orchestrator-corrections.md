# 20R — исправление замечаний приёмки оркестратора

Ты — исполнитель 20R. Этап 20 реализован, но не принят координатором.
Исправь подтверждённые F1–F5 и завершение локальной TestOps цепочки.
Других агентов не запускай; независимое поручение 21 пока не разрешено.

Рабочая папка: `/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Приложение: `/Users/zenalark/PycharmProjects/Test-java/niffler-py-st3` — read-only.

Прочитай AGENTS.md, каталог компонентов и локальный run-tests skill,
задание 20, wave 19, handoff/design 20, runbook qa-workflow/TestOps и
**docs/qa-workflow/handoffs/coordination-wave-20.md целиком**.
Пять собственных воспроизведений координатора:
`artifacts/workflow-implementation/coordinator-20-review-20261115/probe.py`
и `probe-results.json`. Сначала воспроизведи в temp dirs; исторические
пробы/результаты координатора не переписывай. Создай свои regression
tests, проверяющие нужное поведение, а не наличие старых функций.

## Исправления

1. **F1:** неизвестный/dispatched PR create не становится failed/retry-safe
   по zero search. Re-prepare, изменение title/body/files/branches,
   новая ревизия и supersede не снимают незавершённый эффект и не заменяют
   его spec. Сохрани immutable intent со snapshot исходного target/spec
   для reconciliation. Любой новый create того же логического результата
   блокируется до доказанного разрешения старого исхода. Не добавляй
   флаг reset/force или небезопасный recovery. Нет доказательства — blocked.
2. **F2:** единый preflight перед gate/mutation/effect: проверка актуальных
   документов, requirements, app/context/test sources и dependency digests.
   Изменение файлов после init/accept не проходит по старым записанным
   digest. Doctor обнаруживает drift, а run/import/publish/PR не продолжают
   по stale approval. Не требуй ручного init как единственной защиты.
   Import/adopt проверяет точную identity: manifest/run ID/selection,
   app base+patch либо immutable head, tests commit+source snapshot,
   source copies/missing/changed_during_run, ожидаемое окружение/image
   binding и точный состав сценариев/JUnit/Allure по применимому контракту.
   Неполные/чужие evidence не удовлетворяют executed. Само поле
   bound_revision не является доказательством соответствия.
   Для исторического baseline допускается только явная ранее принятая
   provenance/equivalence, привязанная к точным digest evidence; не
   подставляй current source SHA в старый manifest. Разметка ALLURE_ID
   после baseline — исторически принятая правка 17A, не новый baseline.
   Если строгий импорт старого evidence невозможен, явно оставь gate
   blocked, не ослабляй проверки и не запускай baseline заново.
3. **F3:** PR spec содержит известный immutable head и проверяемый состав/
   body/title digest; transport get возвращает данные для точной сверки,
   а не только workflow marker/branches. Missing/mismatched head/spec,
   неполные search/get и несколько кандидатов не дают verified/adopted
   как завершённую публикацию. Совпадение repo/веток — только кандидаты.
   Пока head/spec неизвестны, prepare может оставаться локальным черновиком,
   но verified/published недостижимы. Live transport не добавляй.
4. **F4:** patch head, commit head и base классифицируются относительно
   принятой ревизии и запрошенного варианта. Для patch head требуются
   совпадение base и patch; для commit head — точный head SHA, base не
   выдаётся за head. Проверяй противоречащие run args до dispatch.
   Старые CLI harness и их публичную семантику не менять.
5. **F5:** одинаковый свежий accepted artifact при повторе — no-op во
   всех последующих фазах без повторного compile/list/run/transport.
   Конфликт содержимого/источников не превращай в no-op по одному
   envelope digest. Новый артефакт по-прежнему проходит phase/review gates.
6. **Локальная TestOps цепочка:** подключи plan/assign/package через
   существующий адаптер для нового pending execution, с проверкой
   согласованного mapping и integrity. Добавь resume/verify путь после
   sent/inconclusive, который не вызывает upload. Используй текущие
   execution locks/guards; уже attempted/uploaded execution не
   пересобирается и не меняется ради проверки. Offline regression tests
   должны считать dispatch каждого шага и доказать отсутствие повторного
   upload после сбоя. Если проверка требует внешнего разрешения, CLI
   остаётся gated; локальные tests используют только fake transports.

Проверь и похожие пути, затронутые исправлениями: inherited intents,
старые PR при новом head, различие cached status и чтения execution
state, ошибки транспорта/прерывания. Не обещай exactly-once на сервере.
Разрешение неизвестного исхода не заменяется «оператор нажал prepare».

## Область записи и проверки

Та же область реализации/тестов/каталога/runbook, что у поручения 20.
Новая актуальная документация:
- `docs/qa-workflow/design/20r-orchestrator-corrections.md`;
- `docs/qa-workflow/handoffs/20r-orchestrator-corrections.md`;
- уникальный `artifacts/workflow-implementation/20r-<UTC>/`.

Исторические handoff/design/evidence 19/20, рабочий
`artifacts/workflow/` и accepted TestOps executions/state не менять.
Все smoke/regression состояния — temp dirs или новый собственный store,
не рабочий lineage пилота. Общие workflow README/индекс/план MVP меняет
координатор. Новые fixtures должны иметь полную синтетическую source/
environment/scenario identity; не обходи усиленную validation в тестах.

Добавь regression на каждый воспроизведённый дефект, на F1 полный путь
create timeout → zero reconcile → changed prepare/revision/supersede →
zero search → create count остаётся 1. На F2 отдельно wrong tests commit,
wrong base с правильным patch, missing/changed source/copies, drift
между accept и следующим gate, неверный image/scenario set. На F3
проверь wrong/missing head/body/files/full title и положительный точный
match. На F4 — base/patch/commit по обеим версиям. На F5 — все виды
accept повторно и counters неизменны. Подключённую TestOps цепочку
проверь после каждого crash boundary, включая sent→verify resume.

Запусти targeted offline regressions, затем compile/collection и unit
group штатным harness. До/после сохрани SHA рабочих workflow index/state
и исторических TestOps states/log/package, API source contract и app fix.
Сохрани команды/exit codes/числа/evidence и diff --check/локальные ссылки.

Никаких API/UI/SUT, Docker/Gradle, CI, сети, реальных TestOps writes,
commit/push/PR, новых агентов или переключения/сброса checkout.
Секреты не читать/копировать. Сохрани все чужие незакоммиченные изменения.
Если расширение публичного API helper неизбежно, сначала сформулируй
точный блокер и минимальное изменение; не снимай guards.

Handoff: ready/blocked/needs_decision, версии/SHA входов, по каждому F1–F5
причина/исправление/regression/evidence, реализация локальной TestOps
цепочки, собственные проверки отдельно от прежних, ограничения live.
Не объявляй 20/полный MVP принятыми и не начинай 21; это решение координатора.
