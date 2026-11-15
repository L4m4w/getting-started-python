# 21 — независимое ревью и повтор QA workflow

По запросу пользователя поручение разделено на параллельные
[21A — состояние/evidence](21a-state-and-evidence-review.md),
[21B — эффекты/recovery](21b-effects-and-recovery-review.md),
[21C — CLI/повтор](21c-cli-and-repeat-review.md).
[Правила разделения](../handoffs/coordination-wave-23.md).
Ниже сохранён общий контракт покрытия; вместе с тремя частями отдельного
исполнителя на весь этот документ не запускай. Сводный handoff 21
и итоговая приёмка — координатора после всех трёх отчётов.

Ты — независимый ревьюер 21. Предпочтительно новый исполнитель, не автор
реализации 20/20R/20R2. Других агентов не запускай. Проверь принятое
offline изменение и сквозную идемпотентность на fake transports.

Рабочая папка: `/Users/zenalark/PycharmProjects/Test-java/getting-started-python`.
Приложение: `/Users/zenalark/PycharmProjects/Test-java/niffler-py-st3` — read-only.

## Принятые входы

Прочитай AGENTS.md, план MVP, поручения 20/20R/20R2,
handoff/design 20R2, **docs/qa-workflow/handoffs/coordination-wave-22.md**,
wave 19–21 (история замечаний), knowledge/components/workflow.md,
knowledge/integrations/qa-workflow.md и testops.md. Координатор принял
20 с исправлениями 20R2 как offline-реализацию; это достаточный вход
для 21 без нового запроса приёмки. Полный MVP не завершён.

Exact SHA принятого кода:
`artifacts/workflow-implementation/coordinator-20r2-review-20261115/reviewed-inputs.sha256.json`.
Evidence исполнителя: `artifacts/workflow-implementation/20r2-20261115T195559Z/`.
Пробы/targeted evidence координатора: `coordinator-20r2-review-20261115/`
в том же родительском каталоге. Сначала проверь отсутствие drift принятого
кода. Не выдавай review старой версии за проверку изменившегося дерева.

## Область записи

Только новый `docs/qa-workflow/handoffs/21-independent-workflow-review.md`
и уникальный `artifacts/workflow-review/21-<UTC>/` (свои scripts/tests,
команды/логи/JSON, isolated stores). Pytest cache и штатные новые unit
harness evidence допустимы. Source code, tests/unit, общие README/планы/
каталоги и исторические handoffs/evidence не редактируй. Рабочий
artifacts/workflow и accepted execution state — read-only.

## Что проверить

1. Независимо изучи gates/identity/source+scenario contracts/strict state/
   envelopes, intents/revisions/supersede, index и locks, durability,
   adapters/argv и CLI. Ищи конкретные ошибки, влияющие на требования
   MVP: ложное accepted/executed/published, дубль эффекта, потеря истории,
   невозможность корректного resume или несоответствие реальному формату.
   Не ограничивайся запуском тестов автора и не расширяй scope новой
   архитектурой/неподтверждённым hardening. Findings должны иметь реальный
   trigger, последствия, file:line и минимальное воспроизведение.
2. Повтори один и тот же вход в isolated fake-project/store: init,
   accepted контекст/сценарии/review/implementation/bindings, head/base
   execution, local prepare TestOps, upload+verify, два PR. Счётчики
   эффектов и идентичность lineage/execution/package/PR проверяются до/
   после повтора, а не только по printed status. Human/LLM этапы — явно
   подготовленные envelopes. Положительный fake PR путь — на отдельно
   проверенном commit/tree, не patch digest. Patch/dirty pilot остаётся
   pending/blocked. Offline published обозначай только как simulation.
3. Независимые fault probes: до/после persisted intent, после subprocess
   success до workflow save, unknown PR+zero search+changed spec/revision/
   supersede, upload sent/inconclusive/unknown, crash local prepare на
   каждой границе, конкурентные index/workflow writers, corrupt/missing
   state, stale sources/requirements/bindings и gate-skipping. Существующие
   protections не должны обходиться другим workflow ID/прежним intent.
   Ни один неизвестный эффект не разрешает blind retry.
4. Source/Allure/JUnit evidence: полный versioned allowlist, copies и
   recheck, точная биекция сценариев, разные base/head статусы, UUID/
   bindings/attachments; проверяемая historical baseline acceptance
   ограничена принятым record. Fake fixtures не должны моделировать
   более удобный формат, чем real raw Allure. Повтори read-only
   compatibility с run-ni_5bvnc и run-vzsatlfk, не изменяя эти деревья.
5. Проверь CLI boundary на реальном subprocess в отдельном --store-dir:
   как минимум init/status/doctor/resume/repeated init по реальным
   read-only repo facts, либо минимальный корректный локальный fixture
   repo. Если нужна подготовка нового Git fixture с commit, используй
   доступную fake Git модель: Git commit сейчас не разрешён.
   Не смешивай тест programmatic API с доказательством работы production
   CLI. SUT dispatch не выполнять; argv/adapters проверяй fake runner.
6. Сопоставь документированные команды/exit codes и capabilities с
   реализацией, а catalogue — с публичными API. Различай доказанное
   offline поведение, ручной импорт старого evidence и непроверенные live
   paths. Итог должен помочь обновить 19A: какие source/checks/ограничения
   нужно включить, но сам пакет 19A не переписывай.

## Проверки и отчёт

Используй `.agents/skills/run-tests/SKILL.md`. Выполни нужные targeted
workflow tests и свои probes; полный unit/collection повторяй только
если review выявил конкретную причину, не ради дублирования 402 passed
исполнителя. До/после зафиксируй SHA всего принятого кода, защищённых
state/index/log/manifest (19 SHA) и 15 API source files; для read-only
pilot probe — также tree digest. Сохрани команды/exit codes/counts.
Проверь diff --check обоих репозиториев и ссылки своего handoff.

Не исправляй обнаруженные дефекты в рамках независимого ревью: передай
координатору воспроизведение и рекомендацию. Разрешённая запись только
в своей области. Никаких сети, SUT/API/UI, Docker/Gradle, CI, TestOps
writes, commit/push/PR, новых агентов, переключения/сброса общего checkout.
Секреты не читать/копировать; все чужие изменения сохранить.

Handoff: ready/blocked/needs_decision; SHA проверенной версии; findings
по приоритету с источниками/repro; собственные команды/результаты/evidence;
что подтверждено и что осталось непроверенным; рекомендация по приёмке
21 и актуализации Git/PR-пакета. Отсутствие findings должно опираться на
перечень проверенных свойств и честные ограничения. Live PR criterion
и полный MVP не закрывать по fake tests. После отчёта остановись для
приёмки координатором.
