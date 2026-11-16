# Проверка 21R: A/C приняты, PR lineage требует 21R2

Дата: 2026-11-16 (Europe/Volgograd). **Общая приёмка 21R остаётся
открытой.** 21R-A принят в назначенной области; документационная часть
21R-C принята и актуализирована координатором. В 21R-B подтверждены
исправления прежних конкретных probes, но найден P1 на стыке inherited
resolution и повторного PR create. Следующее поручение —
[21R2](../agent-tasks/21r2-pr-lineage-deduplication.md).
Все исторические handoff и прежние решения сохранены неизменными.

## Проверенная версия и собственные измерения

Прочитаны handoff A/B/C, исправленные state/envelopes/orchestrator,
новые регрессии, runbook/каталог и связанная CLI-обвязка. SHA совпали
с отчётами A/B:

- state.py: `c52ab60c3a54f0648445b46a25700f9d0896c05a2acb4b757aec9cbe80389e43`;
- envelopes.py: `14696422934331cf15114f9303bcb79dc1e074fd9a0b0c7d2dc8418dc5073a69`;
- orchestrator.py: `202ace846fca06c7fc92d124cfaf2cad6fd69d4d899d582ed583bfe234559b0e`.

Evidence координатора:
`artifacts/workflow-corrections/coordinator-21r-review-20261116/`.
`reviewed-inputs.sha256.json` — 17 exact SHA (прежние 13 с тремя
ожидаемыми изменениями + четыре новых tests/consts); сверки в
`verification-summary.json` и `before.json`.

Собственный pytest, exit 0: **129 passed** за 73.10 s:

```sh
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/unit/test_workflow_21r_a.py tests/unit/test_workflow_21r_b.py \
  tests/unit/test_workflow_20r.py::TestF1UnresolvedExternalEffect \
  tests/unit/test_workflow_20r.py::TestF5RepeatAccept \
  tests/unit/test_workflow_20r2.py::TestR4TestOpsCheckpoints \
  -q --basetemp=artifacts/workflow-corrections/coordinator-21r-review-20261116/pytest-temp \
  -o cache_dir=artifacts/workflow-corrections/coordinator-21r-review-20261116/pytest-cache \
  --junitxml=artifacts/workflow-corrections/coordinator-21r-review-20261116/targeted.xml
```

Полный unit/collection координатор не повторял. **511 passed** —
supplementary прогон B; независимо пересчитан его сохранённый JUnit:
511 testcase, failures/errors/skips=0. Это не собственный полный прогон.

Повтор семи scripts из новых копий, каждый exit 0:

- A schema 8/9: единственный false p6 — контроль с phase=executed при
  implied=published, не новый дефект. Forged-published 3/3;
  accept/import 8/8; real evidence compatibility 11/11.
- B 13/13 исходных критериев OK, включая created в той же линии,
  controlled exceptions, base observation и снятие stale inherited
  blocker. Описательные `detail` в побайтной старой копии исторические;
  выводы основаны на актуальных полях outcome/counters.
- C full-chain fake repeat 31/31, concurrency/recovery 24/24. Это
  simulation, а не live-публикация или прохождение рабочего workflow.
- 17 input SHA, 19 protected SHA и 15 API sources совпали до/после;
  пять tree digest harness/TestOps head/base и workflow неизменны.
  Рабочий workflow остался initialized.
- `sh tools/versions.sh` — exit 0, Python 3.13.15/pins OK;
  diff --check обоих репозиториев — exit 0.

## F-21R-B-1 — P1: resolved inherited intent допускает новый create

**Где:** `orchestrator.py:2580–2647` переводит inherited snapshot в
`resolved` по terminal parent intent; `:2561–2578` после этого исключает
его из blockers; `pr_create:2489–2537` при пустом поиске снова dispatches
create, не используя `resolved_in_parent.parent_evidence.number` для
проверки известного remote PR.

**Воспроизведение:**
`.venv/bin/python artifacts/workflow-corrections/coordinator-21r-review-20261116/inherited-zero-search.py`
— exit 0 означает, что проба выполнена; её safety assertion **не прошёл**.

Используется `TestF2InheritedIntents.test_child_incompatible_spec_not_published`
из нового regression-файла B: новая commit-head lineage доведена до
executed, Git commit/tree корректны. Единственное изменение условия:
после успешного parent adoption транспорт перестаёт видеть PR в search;
его get-map по прежнему номеру сохраняется, create считает remote effects.

1. Parent intent unknown → supersede.
2. Reconcile parent доказывает и усваивает **PR #42**, intent completed.
3. В child inherited snapshot становится resolved; pr_prepare допустим.
4. Search child возвращает [] (лаг/фильтрация), хотя #42 существует.
5. Child выполняет новый **create → PR #101**.

Факты в `inherited-zero-search.json`: remote_numbers=[42,101],
child transport calls=[search,get,search,create,get]. Parent #42 был
прочитан targeted get при adoption; перед новым create targeted get
известного parent number не выполнялся. Новая запись осталась created
(get для #101 не подтверждён), что не отменяет второго внешнего эффекта.

Готовый тест B проверяет только непустой search, видящий parent ref.
Вариант [] воспроизводит именно запрещённое пунктом 2 сводного 21
поведение: разрешение parent снимает stale blocker, но теряет защиту
от дубля его remote effect. Happy-path fake repeat этого не покрывает.

**Решение:** сохранить durable связь с известным remote effect после
resolution, включая повторный prepare/revision/supersede. Targeted get
может доказать adoption только при текущем exact spec/commit/tree;
несовместимость, None/404/error и пустой search не разрешают create.
Историю не удалять. Проверить обе PR-роли и дальнейшую цепь supersede;
terminal `completed` не равнозначен «эффекта не было».

## Решения по A/B/C и документации

- A F1/F2/F5 приняты: type/domain validation, обязательные роли/required,
  bool-ID rejection, clean CLI 69 на повреждённых копиях state.
- B: base rebind, boundary-token node IDs, controlled errors, head-only
  publication observation и same-lineage created guard подтверждены на
  проверенных путях. Общую PR-idempotency часть не принимать до 21R2.
- C F1 и исправления каталога приняты как документационная работа.
  Pending-разделы актуализированы по реальному A/B коду, remaining
  inherited guard помечен открытым. Новые consts A/B внесены в каталог.
- Уточнение CLI: reconcile/resume могут возвращать exit 0 с локальным
  report action=blocked/error; это не доказательство успешного resolution.
  Corrupt state, который выбрасывает WorkflowBlockedError, даёт 69.
  B проверял controlled report для corrupt upload intent, не отдельный
  subprocess exit 69 этого report-пути. Не заявлять единый 69 для всех
  report-результатов. CLI-код координатор не менял.

HEAD прежние: QA c84483bf6647678d4052eb377e04a682cdaddd74, app
36674280b6878540a9e88f40aaeedf5dfdd2e6ce; оба checkout dirty.
Commit/push/PR не разрешены. API/TestOps 00–18 и ограничения их аудита
сохраняются; upload/close не повторялись. Сети, SUT/API/UI,
Docker/Gradle/CI/live writes и запуска агентов не было.
Full MVP, immutable heads, реальные draft PR, live идемпотентность и
итоговая оценка остаются открытыми. После 21R2 — повторная приёмка,
затем актуализация 19A. A/C заново запускать не требуется.
