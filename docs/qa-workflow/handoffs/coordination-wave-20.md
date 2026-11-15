# Проверка 20: требуется корректировка перед приёмкой

Дата: 2026-11-15. **Этап 20 пока не принят. Поручение 21 не выдаётся.**
Исполнитель предоставил [handoff ready](20-orchestrator-implementation.md),
реализацию и offline evidence. Координатор воспроизвёл пять дефектов,
затрагивающих обязательные уточнения [wave 19](coordination-wave-19.md).
Следующее поручение — [20R](../agent-tasks/20r-orchestrator-corrections.md).
Исторический handoff исполнителя сохранён неизменным.

## Собственные проверки координатора

Прочитаны handoff/design 20, основные модули state/index/locks/envelopes/
adapters/orchestrator, CLI, fixtures и tests intents. Это целевое ревью,
не утверждение об исчерпывающем аудите всех 3273 строк реализации.

Evidence: `artifacts/workflow-implementation/coordinator-20-review-20261115/`:
- `probe.py` — воспроизводимые собственные offline-пробы, только fake
  runner/transports и TemporaryDirectory; рабочие state не меняются;
- `probe-results.json` — пять воспроизведённых нарушений; script exit 1
  означает обнаружение нарушений, не ошибку окружения;
- `reviewed-inputs.sha256.json` — точные SHA рассмотренных исходников,
  handoff/design, рабочего workflow index/state и исторических state;
- `verification-summary.json` — независимый пересчёт сохранённого JUnit.

`sh tools/versions.sh`: exit 0, Python 3.13.15, pins совпали.
Первый локальный вызов `one tests/unit/test_workflow_intents.py` отклонён
argparse (exit 2): wrapper требует node ID метода, не путь файла.
Затем выполнен корректный узкий вызов:

```
sh tools/run-tests.sh one tests/unit/test_workflow_intents.py::TestPrModel::test_unknown_then_zero_search_stays_blocked
```

Exit 0, **1 passed**, собственный evidence `artifacts/harness/run-2ffw09jl/`.
Этот тест не покрывает последующий re-prepare и не опровергает F1.
314 passed/329 collected — результаты исполнителя. Координатор прочёл
manifest/JUnit run-1nfhtki7: 314 testcase без failures/errors/skips,
manifest exit 0; полный unit/collection заново не повторял.

Финальные SHA state/log run-ni_5bvnc совпали с wave 17:
`7bec44e152e68303d85834e3771a125b7639e8c878b391edf9ce54cbde84a13a`,
`0f40d658d5e805e301bd3a7d41e44cf724672c076023967b5e017a2a586135bf`.
API/UI/SUT, Docker/Gradle, CI, сеть, TestOps writes, commit/push/PR и
запуск агентов координатором не выполнялись.

## Подтверждённые замечания

### F1 — P1: re-prepare обходит неизвестный исход PR create

`orchestrator.py:1133–1147` переводит неизвестный create в `failed` на
основании пустого поиска. Затем `pr_prepare:1190–1215` допускает смену
spec у blocked/unknown entry; `_open_pr_intent` больше не видит failed.
Проба: create timeout → empty reconcile → title change через prepare →
create. **Фактически create вызван два раза.** Требование wave 19 —
сохранить unknown/blocked; пустой поиск и смена spec не доказывают,
что первая запись не состоялась. «Явный re-prepare» не является
операторским доказательством отсутствия внешнего эффекта.

### F2 — P1: чужое/неполное evidence удовлетворяет execution gate

`_manifest_matches_revision:785–786` для patch сверяет только patch SHA,
не app base. Import/adopt не сверяют test repository/source identity с
принятой implementation; `doctor` проверяет документы, но не сами test
sources/requirements/context sources. Gate freshness сравнивает записанные
digests друг с другом, а не с изменившимися файлами.

Проба: после accepted implementation изменён test source; manifest
имеет другой tests commit, неверный app_base_sha, отсутствующий
source_identity, container_check performed=false. При совпавшем patch
он импортирован с bound_revision=1; с base evidence **phase=executed,
doctor=[]**. Это не принятие ранее проверенной исторической provenance,
а отсутствие проверки необходимых входов. Проверка package SHA сама по
себе не доказывает соответствие текущим тестам/сценариям/окружению.

### F3 — P1: verified PR без проверки head и состава

`pr_prepare:1204–1209` не сохраняет head_sha; `pr_ref_matches` сверяет
только repo/branches/наличие title_key. `_verify_pr:1403–1406` допускает
отсутствующие head SHA и не сверяет spec/body/files. Проба с теми же
ветками и workflow marker, но другим полным title и произвольным head:
**status=verified**. Такой PR не подтверждает подготовленный результат.
Пока live transport отсутствует, исправление проверяется fake-данными.

### F4 — P2: committed head всегда распознаётся как base

`_manifest_variant:764–765`: любое app_base_sha без patch → base.
Для kind=commit runner передаёт head SHA через существующий flag
app_base_sha, но сопоставление попадает в base-ветку раньше commit-ветки.
Проба с base A/head B: variant=base, matches_current_head=false.
Это блокирует будущий workflow на immutable head; patch и commit
нужно различать с учётом входной ревизии/ожидаемого варианта.

### F5 — P2: повтор accepted артефакта возвращает блокировку

`accept:357–361` проверяет допустимую исходную фазу раньше проверки
идемпотентного повтора. Проба: accept context → context_ready →
тот же accept context. Вместо no-op получен WorkflowBlockedError.
Для implementation повтор также может снова вызвать compile/list до
сравнения digest. Неизменный принятый артефакт должен давать no-op без
повтора выполненных checks, при этом реальный drift должен блокировать.

## Неполнота и границы следующего шага

В handoff честно отмечено: plan/assign/package не включены в orchestrated
TestOps цепочку, live PR отсутствует, реальный run-execution не исполнялся.
Это не повод выполнять live операции. В 20R требуется довести локальную
подготовку TestOps и resumable verify до программного адаптера с offline
проверкой: после sent upload не повторяется, а verify можно продолжить
отдельно. Существующая точечная блокировка upload не заменяет эту цепочку.
Реальный API/TestOps запуск 16–18 сохраняет приёмку и ограничения.

После исправлений — новый handoff 20R и собственная приёмка координатора.
Только затем независимое ревью/повтор 21. До этого этап 20 и полный MVP
нельзя объявлять принятыми. Документационные проверки координатора:
diff --check обоих репозиториев и локальные ссылки новых/обновлённых
документов — OK; исторические входы и рабочий workflow неизменны.
