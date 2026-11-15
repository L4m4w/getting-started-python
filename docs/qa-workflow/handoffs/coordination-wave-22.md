# Приёмка 20/20R2 — offline-реализация оркестратора

Дата: 2026-11-15. **Этап 20 с исправлениями 20R/20R2 завершён и принят
координатором как минимальная offline-реализация.** Это не приёмка
независимой задачи 21, live PR workflow или полного MVP.

Проверены [handoff 20R2](20r2-evidence-and-pr-identity.md), соответствующая
[реализация](../design/20r2-evidence-and-pr-identity.md), contracts/adapters/
orchestrator/state, обновлённые helpers и адресные regression tests.
Прежние остановки [wave 20](coordination-wave-20.md) и
[wave 21](coordination-wave-21.md) сохраняются исторически.

## Собственные измерения координатора

Evidence: `artifacts/workflow-implementation/coordinator-20r2-review-20261115/`.

- `.venv/bin/python -m pytest tests/unit/test_workflow_20r2.py -q
  --junitxml=.../targeted.xml`: **56 passed**, exit 0 (6.83 s).
- `.venv/bin/python -m pytest
  tests/unit/test_workflow_20r.py::TestF1UnresolvedExternalEffect -q
  --junitxml=.../f1-valid-commit.xml`: **3 passed**, exit 0 (1.46 s).
  Это проверка unknown/re-prepare/revision/supersede на пригодном
  commit-head/tree, с исходным create count=1. Старые PR-пробы на patch
  теперь блокируются раньше create; один их зелёный exit не доказывает F1.
- Три probe scripts исполнителя повторены из отдельных побайтных копий
  в новом evidence координатора: original-five-probes/probe/real pilot
  compatibility — **exit 0** каждый. Исторические scripts/results не
  запускались на месте и не переписывались.
- Head run-ni_5bvnc: 6/6 raw Allure сценариев сопоставлены по fullName/
  parameters, manifest problems пусты. Русские display titles не
  участвуют в identity. Baseline run-vzsatlfk: без provenance отклонён
  по двум изменённым в 17A файлам; с закреплённым record problems пусты.
- Деревья head/base harness/TestOps и рабочего workflow до/после
  compatibility-пробы совпали. Это read-only проверка сохранённого
  evidence на синтетическом представлении accepted state, не новый
  API-прогон и не полное прохождение реального workflow через CLI.
- 19/19 защищённых файлов из protected-sha-after исполнителя совпали с
  текущими SHA; все 15 API source files совпали с final manifest.
- Независимо пересчитан JUnit исполнителя run-xjenmsks: 402 testcase,
  failures/errors/skips=0, manifest exit 0, summary согласована.
  **402 passed / 417 collected — измерения исполнителя**, координатор
  полный unit/collection не повторял: targeted проверки достаточны для
  данной приёмки, новых правок кода координатор не делал.

Точные рассмотренные code/handoff/design SHA находятся в
`reviewed-inputs.sha256.json`, сводка — `verification-summary.json`.

## Принятые исправления

- **R1:** versioned source scope, копии и post-run recheck; точная
  JUnit/raw Allure биекция, статусы и bindings, включая разные head/base
  subsets и строгие существующие TestOps results/integrity helpers.
- **R2:** patch digest и dirty snapshot не выдают Git head; неизвестный
  commit/tree оставляет PR spec pending. Проверенные commit fixtures
  используются отдельно от реального незакоммиченного пилота.
- **R3:** запрещён head waiver. Координатор принимает конкретный
  DEFAULT_ACCEPTED_HISTORICAL_BASELINES record для run-vzsatlfk как
  versioned связь уже принятого baseline (wave 5) и эквивалентности
  маркировки 17A (wave 14), с exact evidence/review/source SHA и двумя
  ограниченными changed files. Это не произвольное разрешение менять
  provenance, добавлять record или обходить guards/исторические ограничения.
- **R4:** plan/assign/package boundaries верифицируются по execution
  state, source/mapping/package SHA. Повтор готового prepare не вызывает
  subprocess; потерянный workflow save восстанавливается без package rebuild.
- **F1/F4/F5:** сохранены блок неизвестной PR записи, корректная
  классификация base/patch/commit и идемпотентный fresh accept.

На проверенных путях блокирующих замечаний не осталось. Это результат
целевого координаторского ревью; независимый аудит 21 ещё предстоит.

## Ограничения и следующий шаг

API/TestOps 16–18 остаются принятыми на прежнем evidence, без повторных
внешних операций. Полная live-цепочка оркестратора не выполнялась;
SubprocessRunner на реальном SUT и live PR transport не подтверждены.
Рабочий workflow остаётся initialized; simulation/import не выдаётся за
реальное прохождение всех фаз. Нет immutable head с изменениями, draft PR
и live проверки отсутствия PR-дублей. Итоговая оценка MVP не выполнена.

Следующее поручение — [21: независимое ревью и повтор workflow](../agent-tasks/21-independent-workflow-review.md).
Пользователь передаёт его новому исполнителю; координатор агентов не
запускал. Исправления по итогам ревью — после документированных findings;
независимый ревьюер не меняет реализацию одновременно с проверкой.
Далее — актуализация Git/PR-пакета 19A, конкретная подготовка будущего
разрешения Git writes и итоговая оценка. Commit/push/PR не разрешены.

Координатор не выполнял API/UI/SUT, Docker/Gradle, сеть, CI, TestOps writes,
commit/push/PR. Исторические артефакты и рабочие state не изменял.
Обновлены текущие README/индекс и статус MVP; diff --check обоих репозиториев
и локальные Markdown-ссылки новых/изменённых документов — OK.
