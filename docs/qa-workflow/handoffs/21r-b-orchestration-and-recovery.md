# 21R-B — исправления orchestration/recovery (21B F1–F6, 21A F3/F4)

Дата: 2026-11-15. Исполнитель: 21R-B. **Статус: `ready`** — все назначенные
findings исправлены, новые регрессии и повторные пробы зелёные,
integrity-сверки чистые. Это не приёмка 21R и не разрешение Git/PR-этапа:
общая проверка объединённой версии A+B+C остаётся координатору. Другие
агенты не запускались; все проверки offline на fake runner/transport/Git и
isolated stores. Никаких живых Git/PR/TestOps операций не выполнялось.

## Область и SHA

Изменён один назначенный файл:

| Файл | SHA-256 |
| --- | --- |
| `infrastructure/workflow/orchestrator.py` | `19e506b9…fe3e3e` → **`202ace846fca06c7fc92d124cfaf2cad6fd69d4d899d582ed583bfe234559b0e`** |
| `tests/unit/test_workflow_21r_b.py` (new) | `d976dfd3065b734457a19cbf820dfc019154e99be93fe895b36641466bf0c0a7` |
| `test_data/consts/workflow_21r_b.py` (new) | `7578e08560d9659acc429f43375a90a732441713b98f54dd2677e4c77b587dfc` |
| `docs/qa-workflow/handoffs/21r-b-orchestration-and-recovery.md` (new) | этот файл |
| `artifacts/workflow-corrections/21r-b-20261115T204209Z/` (new) | gitignored evidence |

`index.py`/`locks.py` не трогались — вне области записи задания.

Сверки до/после (`reviewed-inputs-{before,after}.json`,
`protected-sha-{before,after}-check.txt`, `api-sources-{before,after}.json`):

- `reviewed-inputs.sha256.json`: **10/13 MATCH**. Ровно три ожидаемых
  изменения: `orchestrator.py` — моё (назначенный файл); `state.py`
  (`c52ab60c…89e43`) и `envelopes.py` (`14696422…73a69`) — peer-изменения
  21R-A, причём текущие SHA байт-в-байт совпадают со значениями,
  зафиксированными в handoff 21R-A, т.е. это та же самая версия, а не
  новый drift. Документы 20R2 и остальные файлы совпадают с принятым
  baseline.
- **19/19** protected SHA из `20r2-20261115T195559Z/protected-sha-after.txt`
  совпали до и после (index.json, wf-17431cddc9919d3d, TestOps states,
  upload.log, manifest/junit runs, пробы координатора).
- **15/15** API sources совпадают с `source_identity` manifest
  `run-ni_5bvnc`.

## Исправления (findings → код → проверки)

### 21B F1: `created` PR не пересоздаётся без доказательства

- `pr_create`: entry `created` с записанным `number` больше не уходит в
  повторный search→dispatch. Новый `_reprove_created_pr` делает только
  targeted `get(repo, number)` + `_verify_pr` (Git commit/tree + exact
  content): exact → `verified`; None/404 → `blocked`; mismatch → `blocked`;
  transport error → `unknown`/75. Во всех ветках `create` вызывается 0 раз,
  записанный номер не теряется. Даже доказанное отсутствие PR не
  авторизует новый create автоматически.
- `pr_prepare`: статусы `created`/`verified`/`intent` блокируют замену spec.
- Revision/supersede не деградирует `created` в retryable: `apply_revision`
  переводит entry в `blocked`, `pr_create` отказывает до reconcile.

Пробы: P1 (created + пустой search → blocked, remote_pr_count=1), P2
(exact → verified без второго create), P3 (unknown + rev2 + supersede →
blocked по всем путям, create_calls=1).
Тесты: `TestF1CreatedTargetedGet` — 12 кейсов на обе роли app/tests:
get None/error/mismatch/exact, re-prepare, unknown/created через смену
ревизии; counters — `len(_creates(transport)) == 1`.

### 21B F2: inherited intents пересверяются с parent-линией

- Новые `_blocking_inherited`, `_refresh_inherited_intents`,
  `_inherited_parent_verdict`: унаследованный снимок перечитывается по
  parent-state (read-only, без лока parent — обратного порядка
  lock/взаимной блокировки нет). Resolution засчитывается только когда
  parent == записанный `supersedes`, state грузится чисто и несёт ТОТ ЖЕ
  intent (id + operation + идентичный target) в terminal-статусе; запись
  помечается `resolved` с `resolved_in_parent` — история сохраняется.
  Missing/corrupt parent, отсутствующий intent или intent с другим target
  под тем же id — ambiguous → блокер остаётся. Remote-эффект parent'а
  новой линией не редиспатчится; refresh выполняется в `reconcile`,
  `pr_prepare`, `pr_create`.

Пробы: P9 — parent adopted → inherited `resolved`, новая линия prepare
`prepared` (ранее вечный блок).
Тесты: `TestF2InheritedIntents` — adopted→prepared (counters: parent
dispatch=0 на resolving transport), unresolved→blocked, corrupt/missing
parent→blocked, target-mismatch под тем же id→blocked, commit-head
линия→executed с несовместимым spec → foreign search → blocked, reconcile
тоже пересверяет.

### 21B F3/F4: контролируемые исходы reconcile/create

- `_reconcile_pr`: spec читается из неизменного snapshot в intent.target
  (не из позднего entry); missing/invalid spec → controlled `blocked`
  report до любого search; `transport.search` exception → `blocked`,
  intent остаётся unfinished и никогда не конвертируется в retry-safe.
- `reconcile`: per-intent `save_state` после каждого решения — поздний
  сбой не теряет ранее доказанные resolutions; crash конкретного intent
  → action `error`, остальные продолжают.
- `pr_create`: `search` exception → controlled `blocked`/69 до dispatch,
  entry не poisoned (остаётся `pending`), create=0.

Пробы: P6 (missing spec — controlled, не KeyError), P6b (search raise —
controlled, reconcile не умирает).
Тесты: `TestF34ControlledBoundaries` — missing spec (transport.calls==[]),
search exception в reconcile и в create, adopted-до-crash переживает
поздний blocked (ранний `completed` intent сохранён).

### 21B F5: corrupt TestOps state — контролируемый 69

- `verify_testops`, `prepare_testops`, `publish_testops`,
  `import_execution`/`_reimport_recorded_execution`,
  `_reconcile_upload`, `_observe_testops` ловят `StateCorruptError` →
  `WorkflowBlockedError` (CLI 69) или controlled `blocked` report.
  Байты файла не изменяются, dispatch=0.

Пробы: P7 (verify/prepare/publish — blocked-69, reconcile — controlled,
bytes неизменны), P7b (corrupt при reconcile upload — blocked report).
Тесты: `TestF5CorruptTestOps` — verify/prepare/publish 69 + dispatch
counters заморожены + bytes неизменны; reconcile — blocked, intent
остаётся dispatched.

### 21B F6: наблюдение base не перезаписывает head publication

- `_observe_testops` резолвит variant execution'а (явный параметр или из
  записей): `variant == "base"` → только возврат прочитанного state,
  `publications.testops` не переписывается — через verify, reconcile,
  import или любого другого caller'а. Канал публикации принадлежит
  текущему head; уже подтверждённое наблюдение не деградирует.

Пробы: P8 — `verify_testops(base)` после uploaded head: obs остаётся
`run-unithead1`, phase `executed` сохранён.
Тесты: `TestF6BaseObservation` — verify(base) → `execution_id`/`state_sha256`
канала неизменны; published-фаза переживает base uploaded; reconcile
base-upload-intent → adopted, но канал остаётся head.

### 21A F3: re-import записанного execution

- Новый `_reimport_recorded_execution`: bound==revision → честный `no-op`;
  head прошлой ревизии → `blocked` (never reused — нужен новый run);
  только `base` может перевязаться, и только после полной повторной
  проверки свежего import'а (manifest, junit recount, TestOps source
  integrity, preflight, scenario/source/environment/provenance identity).
  Противоречие provenance с записанным acceptance → blocked. Rebind —
  audit-событие `base-rebind` в журнале (`rebound_from_revision`),
  evidence и история не переписываются; повтор — no-op.

Тесты: `TestBaseReimport` — rebound после T8 (`bound_revision` 1→2,
phase executed, журнал содержит `base-rebind`), same-revision no-op,
head bound=1 → blocked без `rebound_*`, drift копии источника → blocked,
provenance conflict → blocked.

### 21A F4: boundary-token matching node IDs

- `_node_id_covers`: сценарий покрывается только при совпадении по
  boundary-токену; `UNIT-VAL-0010` не покрывает `UNIT-VAL-001`,
  реальные параметризованные `…::test_case[UNIT-VAL-001]` покрывают.

Тесты: `TestNodeIdBoundary` — lookalike-набор из list-вывода отклонён
`WorkflowBlockedError` с упоминанием `UNIT-VAL-001`; реальные node IDs
→ `accepted`.

## Выполненные проверки

| Команда | Exit | Результат |
| --- | --- | --- |
| `pytest tests/unit/test_workflow_21r_b.py` (isolated basetemp/cache/junit) | 0 | **35 passed** |
| `pytest 20r::TestF1UnresolvedExternalEffect 20r::TestF5RepeatAccept 20r2::TestR4TestOpsCheckpoints` | 0 | **20 passed** |
| `pytest test_workflow_intents.py test_workflow_20r.py test_workflow_20r2.py test_workflow_21r_a.py` | 0 | **187 passed** (21r_a — supplementary, см. ограничения) |
| `pytest tests/unit` (supplementary smoke общего компонента) | 0 | **511 passed** |
| `21b …/probes.py <новый каталог>` | 0 | **13/13 OK** |
| `21c full_chain_repeat.py` (копия, EV → новый evidence) | 0 | **31/31 checks, 0 failed** |
| `shasum -a 256 -c protected-sha-before.txt` | 0 | 19/19 OK |
| py_compile оркестратора + тестов; скан trailing whitespace | 0 | чисто |

Все прогоны pytest — с собственными `--basetemp`/-o `cache_dir`/`--junitxml`
под evidence-каталогом; `21C` проба — из копии скрипта с перенаправленным
`EV`, исходные evidence ревью не переписывались.

## Dispatch counters (до/после)

| Проверка | Инвариант | Факт |
| --- | --- | --- |
| P1/P2, `TestF1CreatedTargetedGet` | повторный `create` запрещён | create=1 на всю цепочку; `remote_pr_count`=1 |
| P3 (unknown + rev2 + supersede) | ни один путь не редиспатчит | `create_calls`=1 |
| P4 (sent/unknown/in_progress/uploaded/failed) | publish блокирует до dispatch | `testops-calls`=0 на каждый статус |
| P4b (unconfirmed verify) | verify не вызывает re-upload | `upload_calls`=0 |
| P5 (crash после каждого шага prepare) | resume не повторяет завершённые шаги | dispatched == expected (`plan`→[assign,package], `assign`→[package], `package`/`never`→[]) |
| P10 (run crash после subprocess до save) | evidence adopted, run не повторяется | `pytest_dispatches`=1, `reconcile`=`adopted` |
| 21C chain A repeat | счётчики runner/transport заморожены | runner calls 8→8; `create` на обоих transport без новых вызовов |
| `TestF34ControlledBoundaries` | missing-spec reconcile не вызывает search | `transport.calls == []` |

## Новые константы

`test_data.consts.workflow_21r_b` — только данные моих тестов:
`EXECUTION_HEAD_2`/`EXECUTION_BASE_2`/`EXECUTION_HEAD_3`,
`PR_CREATED_NUMBER`/`PR_PARENT_NUMBER`/`PR_URL_TEMPLATE`,
`HEAD_BRANCH`/`BASE_BRANCH`, заголовки spec, `CORRUPT_STATE_BYTES`,
`MUTATED_SOURCE_TEXT`, `PROVENANCE_A`/`PROVENANCE_B`.
Shared consts/fixtures/утилиты не изменялись.

## Поведенческие заметки (границы решения)

- `_reprove_created_pr` осознанно не делает fresh search: записанный
  `created`-эффект редоказывается только targeted `get` по номеру —
  search может пропустить реально созданный PR (eventual consistency),
  что и было первопричиной дубликата в P1.
- `_inherited_parent_verdict` читает parent-state без лока: parent
  superseded (терминален для новых записей), чтение не создаёт обратного
  порядка блокировок; любая неоднозначность трактуется как блокер.
- Re-import head-execution прошлой ревизии отклонён по определению —
  сравниваемость head-доказательств требует нового run, а не rebind.
- `verify_testops` по-прежнему возобновляется только из durable `sent`;
  `uploaded` — no-op; всё остальное — 69 до dispatch.

## Ограничения и непроверенное

- Назначенные сабсеты выполнены полностью; дополнительно (сверх задания,
  как smoke общего компонента после peer-изменений 21R-A) прогнан весь
  `tests/unit` — 511 passed, и файл 21R-A в составе subset-прогона —
  187 passed. Эти прогоны помечены supplementary; объединённую версию
  A+B+C формально проверяет координатор.
- Живые пути не трогались: сеть, SUT/API/UI, Docker/Gradle/CI,
  TestOps/PR writes, commit/push/checkout/reset — не выполнялись;
  приложение, рабочий workflow и исторические evidence — read-only
  (19/19 protected, 15/15 API, 10/13 reviewed-inputs с тремя ожидаемыми
  дельтами).
- `workflow.py` CLI-обвязка новых веток не тестировалась end-to-end —
  все исходы проверены на уровне оркестратора/fake transports;
  real-transport wiring — будущая авторизованная работа.
- Peer drift на момент handoff: `state.py`/`envelopes.py` соответствуют
  зафиксированным в 21R-A SHA; дальнейшие правки A/C после моей сверки
  проверяются координатором при слиянии.

## Заметки для 21R-C (каталог/документация)

- `orchestrator`: новые приватные методы `_reprove_created_pr`,
  `_blocking_inherited`, `_refresh_inherited_intents`,
  `_inherited_parent_verdict`, `_reimport_recorded_execution`;
  `_observe_testops` получил параметр `variant` и больше не пишет
  `publications.testops` для base-наблюдений.
- `reconcile` пересверяет `inherited_intents` до цикла intents и
  сохраняет state после каждого решения; report-экшены: `adopted`,
  `blocked`, `retryable`, `kept`, `error`, `ignored`.
- `import_execution` на уже записанном execution: `no-op` (та же
  ревизия), `rebound` (base после полной проверки), `blocked` (head
  прошлой ревизии / drift / provenance-conflict).
- Новый модуль констант `test_data.consts.workflow_21r_b` и регрессии
  `tests/unit/test_workflow_21r_b.py` (35 тестов, обе PR-роли
  параметризованы, dispatch counters во всех ветках).

## Остановка

После этого handoff работа прекращена до общей приёмки координатором
всех частей 21R; никакого Git/PR/TestOps-этапа не инициировалось.
