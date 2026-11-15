# 21R2 — PR lineage deduplication после разрешения parent intent

Дата: 2026-11-15 (UTC). Исполнитель: 21R2. **Статус: `ready`** —
назначенный P1 F-21R-B-1 исправлен, координаторская проба из новой
копии проходит с safety assertion `passed`, назначенные регрессии и
повторные пробы зелёные, integrity-сверки чистые. Это не приёмка 21R и
не разрешение Git/PR-этапа: общая проверка объединённой версии и
актуализация 19A остаются координатору. Другие агенты не запускались;
все проверки offline на fake runner/transport/Git и isolated stores.

## Область и SHA

| Файл | SHA-256 |
| --- | --- |
| `infrastructure/workflow/orchestrator.py` | `202ace846fca06c7fc92d124cfaf2cad6fd69d4d899d582ed583bfe234559b0e` → **`f9e9d312c889b9f7a896132ddcf1624d1734d98d468cc1b9f17c607267d78607`** |
| `tests/unit/test_workflow_21r2.py` (new) | `b8edae78e9fd27a003dc386a2276cd2806d2559fe942fc77ddc4839e94343c4c` |
| `test_data/consts/workflow_21r2.py` (new) | `70bdf8f78ed0f165d7c2c6edb498f84e3d9090c654baef0d205dee68fab7c31e` |
| `knowledge/components/workflow.md` | `598b7614…28` → `1895cd6d298a67aa05d9525875241b841791be174346d1a54ad782a67cb2e4fe` |
| `knowledge/components/consts.md` | `7bcea462…55` → `8bc8685269c7c745b78102d312cf5e2b6276a4145b8892c4c567605f1e9b79ca` |
| `knowledge/integrations/qa-workflow.md` | `ea4b8a00…f6` → `d329f19014570264d4d4f099119fa887a015079b08574fc799f1c61af167f6fb` |
| `docs/qa-workflow/handoffs/21r2-pr-lineage-deduplication.md` (new) | этот файл |
| `artifacts/workflow-corrections/21r2-20261115T211831Z/` (new) | gitignored evidence |

State/envelopes/contracts/adapters/index/locks/CLI не трогались — вне
области записи. Старые tests/fixtures/consts, исторические handoffs и
evidence не изменялись; все незакоммиченные изменения peer-работ
сохранены (на момент handoff peer drift в назначенных мне файлах не
наблюдался — baseline `reviewed-inputs.sha256.json` совпал 17/17 до
правок).

## Root cause и решение

**Дефект (F-21R-B-1).** Разрешение inherited snapshot по terminal
parent intent снимало blocker целиком: `resolved_in_parent` записывал
`parent_evidence` с известным номером PR, но `pr_create` после refresh
опирался только на unfinished snapshots + свежий `search`. Пустой
search (лаг/фильтрация) разрешал второй `create`: parent adopted #42 →
child executed → search [] → create #101. Те же дыры были у terminal
effect'ов, записанных до supersede (переносились только unfinished
intents), и у второго supersede (grandparent→parent→child терял и
unresolved ancestry, и resolved evidence).

**Решение (в `orchestrator.py`, без новой архитектуры).**

1. `init --supersede` наследует из superseded state: (а) все
   `inherited_intents` parent'а как есть — unresolved остаются
   блокерами, resolved хранят доказательство; (б) terminal `pr.create`
   intents с записанным `evidence.number` — как already-resolved
   snapshot с `resolved_in_parent` (honest verdict: intent уже
   терминален и идентичен). Пометка `blocked` у `publications.pr` по-
   прежнему ставится только для unfinished наследников.
2. `_inherited_parent_verdict` резолвит `inherited_from` через новый
   `_ancestor_state` — обход записанной цепочки `supersedes` (до 32
   hop, защита от циклов): parent/grandparent читаются без lock'ов,
   missing/corrupt/ambiguous → verdict `None` → fail-closed blocker.
3. `pr_create` до свежего search и dispatch вызывает
   `_reprove_lineage_pr` по номерам из `_lineage_pr_numbers` (снимок
   `resolved_in_parent.parent_evidence` + собственное `evidence`
   наследников, int без bool, дедупликация). Каждый номер
   редоказывается targeted `transport.get` + `_verify_pr` к **текущему**
   spec (commit/tree/exact-spec guards): exact → adoption `verified` с
   завершением open declared intent; несовпадение или None/404 →
   `blocked` (записанный эффект сохраняется, recreate не разрешён);
   ошибка get → `unknown` (75). Свежий search в этой ветке не
   выполняется — он не может доказать отсутствие известного эффекта.
   Собственный `created` entry по-прежнему обрабатывается
   `_reprove_created_pr` раньше и побеждает.

История не удаляется: resolved snapshots и verdict'ы остаются в
`inherited_intents`; успешный create не переводится в failed/retryable.

## Проверки и evidence

Evidence root: `artifacts/workflow-corrections/21r2-20261115T211831Z/`
(далее `<EV>`).

| Команда | Exit | Результат |
| --- | --- | --- |
| `.venv/bin/python <EV>/inherited-zero-search.py` (копия пробы координатора) **до** fix | 0 | assertion НЕ прошёл: `remote_numbers=[42,101]`, child calls `[search,get,search,create,get]` — дефект воспроизведён |
| то же **после** fix (store пересоздан) | 0 | `assertion: passed`, `remote_numbers=[42]`, child calls `[search,get,get,get]` — targeted get #42 + внутренний get verify, ни search, ни create; см. `<EV>/inherited-zero-search.json` |
| `pytest tests/unit/test_workflow_21r2.py` (own basetemp/cache/junit) | 0 | **24 passed** — `<EV>/junit-21r2.xml` (24 testcase, 0 failures/errors/skipped) |
| `pytest test_workflow_21r_b.py test_workflow_intents.py test_workflow_20r.py::TestF1UnresolvedExternalEffect test_workflow_20r2.py::TestR2GitHeadSeparation` | 0 | **75 passed** — `<EV>/junit-regression.xml` (75, 0/0/0) |
| `<EV>/full_chain_repeat.py` (копия 21C-пробы, EV → свой каталог) | 0 | **31/31 checks, 0 failed** — `<EV>/full-chain-repeat-results.json` |
| `sh tools/versions.sh` | 0 | Python 3.13.x, pins OK — `<EV>/versions.txt` |
| `sh tools/compile-tests.sh` | 0 | 550 collected, без выполнения — `<EV>/compile-tests.txt` |
| `shasum -a 256 -c <EV>/protected-sha-before.txt` | 0 | **19/19 OK** — `<EV>/protected-sha-check.txt` |
| API sources manifest `run-ni_5bvnc` | — | **15/15 совпали** (тот же вывод в check-файле) |
| `git diff --check` | 0 | чисто — `<EV>/diff-check.txt` |
| reviewed-inputs baseline | — | до: 17/17 MATCH; после: 16/17 MATCH, единственный DIFF — назначенный `orchestrator.py` (`<EV>/before-sha.txt`, `<EV>/after-sha.txt`) |

Общий unit/collection и supplementary прогоны не повторялись — задание
их не требовало; рабочий workflow остался initialized.

## Dispatch counters (до/после)

| Проверка | Инвариант | Факт |
| --- | --- | --- |
| Проба координатора (resolved parent + search []) | второй create запрещён | до: remote `[42,101]`; после: remote `[42]`, child `create` вызовов **0**, targeted `get` `#42` вместо dispatch |
| `TestR2ResolvedParentLineageGuard` ([] / get None / error / mismatch / exact, обе роли) | create counter не растёт | `len(_creates(resolving))==0`, `len(_creates(parent_transport))==1` во всех ветках; exact ref → `adopted`+`verified`, повтор → `no-op` |
| Re-prepare и revision+re-prepare после blocked | guard сохраняется | повторные create=0, snapshot `resolved` с номером не теряется |
| Terminal verified #57 до supersede | эффект наследуется resolved-снимком | `resolved_in_parent.parent_evidence.number==57`, `inherited_from==old_id`, create=0 |
| Two-hop unresolved ancestry | fail-closed до разрешения grandparent | prepare child `blocked` 69; после adopted grandparent resolution доходит через цепочку `supersedes`, create=0 |
| Контроли: первая линия без ancestry; supersede без PR-эффекта | обычный create работает | `verified`, `len(_creates)==1` в обеих ролях |
| 21C full-chain repeat | счётчики заморожены | 31/31 — runner/transport без новых dispatch |

## Новые константы и регрессии

`test_data.consts.workflow_21r2` — только данные моих тестов:
`APP_BASE_SHA_3`/`APP_HEAD_COMMIT_SHA_3` (третья линия),
`PR_LINEAGE_NUMBER`=42, `PR_TERMINAL_NUMBER`=57,
`EXECUTION_HEAD_4`/`EXECUTION_HEAD_5`/`EXECUTION_BASE_3`/`EXECUTION_BASE_4`.
Shared consts/fixtures/утилиты не изменялись; константы 21R-B
переиспользованы по ссылке.

`tests/unit/test_workflow_21r2.py` — 24 теста, обе PR-роли
параметризованы, счётчики create/get во всех ветках, проверки на
достижимых путях (child доводится до executed на корректных commit/tree
fixtures — фазный отказ initialized как проверка не засчитывался).

## Документация

- `knowledge/components/workflow.md` — раздел «Проверка 21R» описывает
  реальные API 21R2 (`_ancestor_state`, `_lineage_pr_numbers`,
  `_reprove_lineage_pr`, расширенное наследование при supersede) и снят
  pending «inherited guard не принят»; общая приёмка явно оставлена
  координатору.
- `knowledge/components/consts.md` — запись `workflow_21r2`.
- `knowledge/integrations/qa-workflow.md` — контракт-пункт inherited
  guard переведён из «целевой контракт» в реализованную семантику.

## Поведенческие заметки (границы решения)

- Редоказательство lineage-эффекта не делает fresh search по дизайну —
  search может пропустить реальный PR (та же причина, что в 21B F1).
- Adoption через ancestry требует exact match к **текущему** spec:
  ref со старым head/title_key чужой линии не adopt'ится → blocked и
  ручное разрешение, как и для foreign-кандидатов из search.
- Доказанный 404/несовместимость/error никогда не авторизуют новый
  create; повторный `pr_create` после blocked требует re-prepare
  (entry blocked), после unknown — свободный повтор targeted get.
- Terminal parent intent без `evidence.number` ничего в guard не
  добавляет — переносятся только записанные эффекты; `failed` со
  `superseded_spec` (без dispatch) номера не имеет и остаётся просто
  историей.

## Ограничения и непроверенное

- Назначенный набор выполнен полностью; `test_workflow_21r_a.py` и
  общий unit/collection без причины не повторялись (зафиксированный
  baseline A/C не менялся — 16/17 MATCH после правок, единственный
  DIFF — назначенный файл).
- Живые пути не трогались: сеть, SUT/API/UI, Docker/Gradle/CI,
  TestOps/PR writes, commit/push/checkout/reset — не выполнялись;
  приложение, рабочий workflow, accepted execution state и исторические
  evidence — read-only (19/19 protected, 15/15 API sources, originals
  не запускались на месте — все пробы из копий в собственном `<EV>`).
- `workflow.py` CLI-обвязка новых веток не прогонялась subprocess'ом —
  исходы проверены на уровне оркестратора/fake transports;
  real-transport wiring — будущая авторизованная работа.
- Verdict-обход ограничен 32 hop'ами записанной цепочки `supersedes`;
  более глубокая или сломанная история остаётся fail-closed blocker'ом.

## Остановка

После этого handoff работа прекращена до общей приёмки координатором:
актуализация 19A и решение о Git/PR-этапе — не мои.
