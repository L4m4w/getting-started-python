# 21C — независимое ревью: CLI, index/locks/concurrency, повтор полной цепочки

Дата: 2026-11-15. Исполнитель: независимый ревьюер 21C (не автор 20/20R/20R2).
**Статус: `ready`** — ревью завершено; зафиксировано 1 finding уровня low
(документационный пробел) и замечания без дефектов. Код не изменялся;
другие агенты не запускались; все операции offline; SUT/TestOps/Git/PR
записи не выполнялись.

Параллельные области: state/envelopes/evidence — 21A; эффекты/recovery —
21B. Этот отчёт покрывает только назначенную часть 21C и **не** является
приёмкой задачи 21 или MVP.

Evidence root: `artifacts/workflow-review/21c-20261115T201234Z/` (далее `<EV>`).

## 1. Проверенная версия (SHA)

- **Accepted code**: все 13 записей `coordinator-20r2-review-20261115/
  reviewed-inputs.sha256.json` пересчитаны **до и после** ревью — совпали,
  drift отсутствует. `<EV>/baseline-check.json`, `<EV>/baseline-check-after.json`.
- **Protected state**: 19/19 SHA из `20r2-20261115T195559Z/protected-sha-after.txt`
  совпали до и после (index.json, wf-17431cddc9919d3d/state.json, TestOps
  state×3, upload.log×2, manifest/junit×6, coordinator probes×4).
- **API source**: `snapshot_allowlist` по 15 файлам `api-contract-v1` =
  `f1c6d812fbdaec8ba24c28c88677e5a608c88d95a2cce5f9dba86420c1ba50af` —
  совпал с записанным в реальном state и с auto-compute в изолированном
  CLI store. `<EV>/api-snapshot-after.json`.
- Untracked отчёты 21A/21B/21C **не** вызвали ложного drift (см. §4.4).

Ключевые SHA-256 (первые 16): `orchestrator.py 19e506b9e88a5c7a`,
`state.py a7c85ee1df724881`, `index.py 305f3fa2ef56c367`,
`locks.py 851cd1b74bc991d3`, `adapters.py 9a9b23a51227d1d3`,
`envelopes.py 8caf13c304186729`, `contracts.py e1caf5c78c3bee51`,
`tools/workflow.py 489bf41a14641497`, `tools/run-workflow.sh 1de31a27c389fd4c`.

## 2. Назначенные тесты (через run-tests skill, private basetemp/cache/junit)

Версии: Python 3.13.15, pytest 9.1.1, allure-pytest 2.16.2,
selenium 4.51.0 (`sh tools/versions.sh`, exit 0; SUT NOT_VERIFIED — не требовался).

| Команда (все с `--basetemp=<EV>/tmp/... -o cache_dir=<EV>/...`) | Exit | Результат | JUnit |
| --- | --- | --- | --- |
| `pytest tests/unit/test_workflow_orchestrator.py` | 0 | **14 passed**, 3.64s | `<EV>/junit/orchestrator.xml` |
| `pytest tests/unit/test_workflow_state.py::TestIndex` | 0 | **3 passed** | `<EV>/junit/state-index.xml` |
| `pytest tests/unit/test_workflow_20r.py::TestF5RepeatAccept` | 0 | **4 passed** | `<EV>/junit/f5-repeat.xml` |

Итого 21 passed, 0 failed/errors/skipped. Тесты не редактировались.

## 3. CLI subprocess smoke (реальный `sh tools/run-workflow.sh`, отдельный `--store-dir`)

Store: `<EV>/cli-store/` (не `artifacts/workflow`). Только read-only факты
репозитория; логи `<EV>/cli-smoke.txt`, `<EV>/cli-smoke-negatives.txt`,
`<EV>/cli-smoke-edge.txt`.

| Команда | Exit | Результат |
| --- | --- | --- |
| `init --pilot-id category-update-validation --app-repo github.com/L4m4w/niffler-py-st3 --app-base-sha 36674280… --app-patch-sha256 04eb4c87… --tests-commit c84483bf… --tests-dirty --app-repo-path ../niffler-py-st3 --requirements …/requirement.md --requirement-ids R1,R2,R3,R4 --expect-head-passed 6 --expect-base-failed 4` | 0 | `created` — **тот же детерминированный id `wf-17431cddc9919d3d`**, что у реального lineage; `revision_data_sha256 8c1d51b3…`, requirements `38d8455…`, auto snapshot `f1c6d812…` — все идентичны записанному реальному state |
| `status` | 0 | phase `initialized`, полный JSON state |
| `doctor` | 0 | `problems: []` |
| `resume` | 0 | `next_step: "accept context <envelope>"` |
| повторный `init` (идентичные аргументы) | 0 | `resumed`, тот же id |
| `check` | 0 | `problems: []`; реальный dispatch `compile-tests.sh` + `run-tests.sh list` (оба exit 0), state не записывается |
| `nonexistent-action` | 2 | argparse invalid choice |
| `init` без `--app-repo/--app-base-sha/--requirements` | 2 | argparse required |
| `accept context <bad envelope>` | 69 | `envelope missing keys: [actor, artifact, envelope_version, payload]` |
| `run-execution --variant head` на `initialized` | 69 | фазный gate до dispatch |
| `publish-testops --execution run-ni_5bvnc` | 69 | фазный gate до dispatch |
| `pr create --repo app` | 69 | фазный gate до dispatch |
| `status`/`doctor`/`resume` на пустом store | 69 | `no workflow found; run init first`; в пустой store ничего не записано |
| `doctor` на реальном `artifacts/workflow` (read-only) | 0 | `problems: []` — при наличии untracked 21a/21b/21c директорий |

Обертка `tools/run-workflow.sh` → `tools/_python.sh` (`PYTHON` >
`.venv/bin/python` > `python3`, cd в корень, `exec`). Exit 0/2/69
воспроизведены реальным subprocess; 75/77/127/130 проверены по коду
dispatch (`tools/workflow.py:26-30,338-354`) и unit-тестами — см. §7.

## 4. Программная симуляция (FakeRunner/FakeGit/FakePrTransport, изолированные sim-roots)

Отделено от §3 по требованию задания. Проб: `<EV>/probes/full_chain_repeat.py`;
результат: `<EV>/full-chain-repeat-results.json` — **31/31 check OK**.
Всё «publication» ниже — SIMULATION на fake transport; реальный
patch/dirty пилот оставлен pending (chain B).

### 4.1 Chain A — commit-head фикстура, полная цепочка → published

Первый проход: init(`commit` head) → accept context/scenarios/review/
implementation/bindings (все `accepted`, explicit envelopes) →
`run_execution("head")` → `recorded run-unithead1` → `import_execution`
→ `imported run-unitbase1 (base, rev 1)` → `prepare_testops` →
`prepared [plan,assign,package]` → `publish_testops --execute` →
`uploaded` → `verify` → `no-op (upload already confirmed)` →
`pr_prepare app/tests` → `prepared, draft=false` → `pr_create` ×2 →
`verified #41` → phase `published`.

| Шаг при повторе идентичного входа | Outcome |
| --- | --- |
| `init` (тот же вход) | `resumed`, тот же `wf-dd04a284aa11e55d` |
| 5× `accept` | все `no-op` |
| `run_execution head/base`, `import_execution`, `prepare_testops` | `BLOCKED` — фазный gate на `published` (69-path) |
| `publish_testops`, `verify_testops`, `pr_prepare` ×2, `pr_create` ×2 | `no-op: already published` |
| `pr_search --online` | `searched`, found=1, ref #41 |
| `reconcile` | `[]` |
| `resume` | `next_step: terminal: nothing to do` |
| `doctor` | `[]` |

### 4.2 Chain B — patch head + dirty tests (зеркало реального пилота)

Доведён до `executed` (head recorded, base imported, prepare run).
`pr_prepare app` → `prepared, draft=true, head_sha=null`;
`pr_prepare tests` → draft (dirty checkout);
`pr_create` ×2 → `blocked, exit 69` — **ни одного transport-вызова**
(блок до search). Фаза осталась `executed`, testops `pending` —
пилот pending, как и требуется.

Повтор: init → `resumed`; accepts → `no-op`; run/import → `no-op`;
`prepare` → `no-op, steps_skipped=[plan,assign,package]` с нулевым
dispatch; `pr_prepare` → `no-op`; `pr_create` → снова `blocked 69`.

### 4.3 Before/after repeat — идентичность и счётчики dispatch

| Свойство | Before → After (A) | Before → After (B) |
| --- | --- | --- |
| Lineage (workflow_id) | `wf-dd04a284aa11e55d` → тот же | `wf-dd04a284aa11e55d` → тот же |
| Revision | 1 → 1 | 1 → 1 |
| Phase | published → published | executed → executed |
| Executions | `run-unithead1/head, run-unitbase1/base` (bound rev 1) → без изменений | то же |
| Intents (id/op/status) | идентичный набор → идентичный | идентичный |
| TestOps `state_sha256` | `976fcc5c…` → `976fcc5c…` | `371a8865…` → `371a8865…` |
| PR spec_sha256 (app) | `f00df743…` → без изменений | `eddf730f…` → без изменений |
| PR spec_sha256 (tests) | `5c754b42…` → без изменений | `273c2fca…` → без изменений |
| PR number/status | #41 verified → без изменений | null/pending → без изменений |
| **FakeRunner calls** | **8 → 8 (+0)** | **6 → 6 (+0)** |
| pr.create transport calls | 1 → 1 (app), 1 → 1 (tests) | 0 → 0 |
| pr transport total | app 3 → 4 (только explicit `pr_search`), tests 3 → 3 | 0 → 0 |

Runner dispatch A (8): compile, list, `group api` (commit sha),
testops plan/assign/package/upload/verify. B (6): то же без
upload/verify. Контрольный случай: повторный `init` с **другим** head
(случайно выполнен в ходе ревью) дал `revisioned` — T8 bump, фаза
упала на `initialized`, каскад stale сработал. Повтор обязан быть
бит-в-бит по входу.

### 4.4 Index/locks/concurrency/recovery — `<EV>/probes/concurrency_recovery.py`

**24/24 check OK** (`<EV>/concurrency-recovery-results.json`):

- **Две независимые линии** в одном store: два pilot_id → два workflow id,
  две active-записи в `index.json`, раздельные state dirs.
- **Второй writer**: `WorkflowLock` удержан → `accept` другого
  Orchestrator → `WorkflowBlockedError` ("locked by pid …") → после
  release тот же op успешен. Reads (`status`) lock-free — только writers
  сериализуются.
- **Stale reclaim**: lock-файл с мёртвым pid → reclaimed, op прошёл,
  lock удалён. Corrupt lock → `LockHeldError` "unreadable or corrupt;
  inspect manually". Non-int pid → "no valid owner pid". Оба — отказ до
  manual inspect, никакого молчаливого удаления.
- **Crash index↔state**: запись `creating` без state dir → повторный init
  = `created` + `mark_active`; `creating` + `superseded` list → link
  `supersedes` восстановлен; `creating` + существующий state → `resumed`
  + active. Параллельная линия не создаётся.
- **Base conflict**: иной `app_base_sha` без `--supersede` →
  `WorkflowBlockedError`; с `--supersede` → новая линия,
  `entry.superseded=[old]`, `state.supersedes=old`, старый state нетронут.
- **Corrupt stores**: обрезанный `index.json` → `WorkflowStateCorruptError`;
  обрезанный `state.json` → `WorkflowStateCorruptError`; подменённый
  `workflow_id` в записи → `BlockedError` "does not match its recorded
  identity" (self-check `orchestrator.py:229-235`); leftover `index.tmp`
  игнорируется.
- **Drift**: untracked `artifacts/workflow-review/21b-fake/*`,
  `artifacts/harness/run-x/*`, `untracked-note.md` внутри sim-root →
  `snapshot_allowlist` digest не изменился (allowlist = только
  `API_SOURCE_FILES`); подтверждено и на реальном store (`doctor` []).

## 5. Documentation/API сопоставление

- **Команды**: parser actions (`tools/workflow.py:236-326`) = 14 действий
  (init/status/accept/check/run-execution/import-execution/
  prepare-testops/publish-testops/verify-testops/reconcile/resume/doctor/
  pr{prepare,create,search}) — 1:1 с runbook
  `knowledge/integrations/qa-workflow.md` и каталогом
  `knowledge/components/workflow.md`. Все маппятся на public-методы
  `Orchestrator` (+ `workflow_dir`), лишних методов нет.
- **Exit codes**: documented `0/2/69/75/77/127/130` совпадают с
  константами и dispatch `tools/workflow.py`; 0/2/69 воспроизведены
  subprocess (§3).
- **Каталог vs API**: все ~60 имён каталога разрешились реальными
  символами модулей state/contracts/envelopes/adapters/locks/index/
  orchestrator/test_data.utils.workflow. Пробелов нет (программная
  сверка, §4 evidence).
- **Publications**: `pr create`/`verified`/`published` на draft-spec
  (patch/none head, dirty tests) — 69 до transport, как задокументировано
  (§4.2). В production CLI live transport не инъецируется — PR-записи
  заблокированы по конструкции.

## 6. Findings

### F-21C-1 [low] Multi-workflow store требует `--workflow-id`, но это не задокументировано

- **File/line**: `infrastructure/workflow/orchestrator.py:113-125`
  (`_resolve_workflow_id`); флаг есть в parser `tools/workflow.py:232`,
  но `knowledge/integrations/qa-workflow.md` и каталог его не упоминают.
- **Trigger**: >1 `wf-*/state.json` в одном `--store-dir` — возникает
  после первого реального `--supersede` (старая линия остаётся) и уже
  сейчас, если параллельные ревьюеры пишут в общий store.
- **Consequence**: все команды без `--workflow-id` (`status`, `doctor`,
  `check`, `accept`, `resume`, executions, testops, `pr *`) отвечают
  `BLOCKED: multiple workflows present; pass --workflow-id` (exit 69).
  После первого supersede runbook-команды перестают работать дословно;
  19A-скрипты обязаны передавать `--workflow-id` явно.
- **Repro**: `<EV>/probes/concurrency_recovery.py` (C1 + попытка
  `status()`/`accept()` без id → `multiple workflows present;
  pass --workflow-id: [wf-…, wf-…, wf-…]`).
- **Fix suggestion** (на усмотрение координатора, не выполнялось):
  задокументировать флаг в runbook или разрешать через index entry
  (`find_entry(repo,pilot)`) при единственной active линии.

## 7. Подтверждённые и неподтверждённые свойства

### Verified (в этой ревизии)

- Детерминизм `wf-<16hex>` и `revision_data_sha256` между независимыми
  stores (реальный и smoke lineage совпали побайтово по revision data).
- Repeat идентичного входа: lineage/executions/intents/package digest/PR
  spec+refs неизменны; **ноль новых dispatch** (runner 8→8, 6→6;
  create-вызовы 1→1/0→0).
- Фазные gates до любого внешнего вызова; draft PR spec никогда не доходит
  до transport.
- Lock order index→workflow (index lock не держится через state-записи
  и делегированные subprocess); single-writer отказ; stale/dead-pid
  reclaim только как mutex; corrupt lock — manual inspect.
- Atomic index/state writes (tmp+fsync+replace+dir fsync); crash между
  регистрацией и записью восстанавливается без параллельной линии.
- Corrupt index/state → `WorkflowStateCorruptError` (69), чужой state
  не перезаписывается.
- Snapshot allowlist исключает untracked review artifacts — ложного
  drift от 21A/21B/21C нет (программно + реальный `doctor`).
- `git diff --check` обоих репозиториев — чисто (exit 0).

### Not verified (вне области или невозможно offline)

- Реальная многопроцессная гонка (отказ второго writer'а проверен
  in-process через тот же file-lock механизм `O_EXCL+flock`).
- Exit 75/77/127/130 реальным subprocess (только code path + unit
  покрытие); fsync против реального отказа питания.
- Любые live-операции: SUT run, TestOps upload/verify, live PR,
  Git commit/push, Docker/Gradle/CI — не выполнялись по заданию.
- Полный unit-suite (402/417 из истории 20R2 не перезапускался —
  не требовался заданием; назначенные 21 тест — выше).

## 8. Ограничения и замечания для пакета 19A (не findings)

- `verify_testops` на уже-uploaded — `no-op`, но обновляет
  `last_observation.checked_at` в state (A: `…:30.60` → `…:31.27`).
  Repeat не бит-в-бит по state-файлу по timestamp; все identity digests
  стабильны. Учитывать при сравнении state после повторов.
- `pr_search --online` делает реальный transport `search` (read-only,
  без записи) — на published это единственный новый вызов при повторе.
- `status`/`doctor`/`resume`/`accept`/`check` и все ops принимают
  `workflow_id` hint только через глобальный `--workflow-id` — см. F-21C-1.
- `tools/_python.sh` без проверки версии интерпретатора: fallback на
  голый `python3` без зависимостей даст неочищенный ImportError,
  а не 69. Для 19A закрепить `PYTHON=.venv/bin/python`.
- `*.lock-gate` файлы (`workflow.lock-gate`, `index.lock-gate`) остаются
  в store после операций — косметика.
- `check` всегда делает реальный delegated dispatch `compile-tests.sh`
  и `run-tests.sh list` (`orchestrator.py:623-629`) плюс doctor +
  пересчёт context digests; state не пишет. На `initialized` это
  единственная команда, запускающая harness — 19A должен учитывать,
  что `check` требует живой venv/tools, а не только state.
- Каталог перечисляет `drive_commit_to_executed` среди модульных helpers
  `test_data.utils.workflow`; это метод `Project` — пример использования
  верный (`project.drive_commit_to_executed()`), косметика.
- 19A: production CLI не принимает live transport; PR publication
  требует `app_head.kind=="commit"` + `tests_repo.dirty==false` —
  реальный пилот (patch+dirty) останется pending до коммита, что и есть
  будущая работа 19A.

## 9. Границы выполнения

- Изменено только: этот handoff + `<EV>/` (probes, sim-stores, logs).
- Не тронуты: исходники, tests/unit, общие README/plans/catalogues,
  исторические handoffs/evidence, `artifacts/workflow` (только read),
  `artifacts/testops`, `artifacts/harness`. Все 75 строк `git status`
  — pre-existing изменения из более ранней работы, сохранены.
- Не выполнялось: code fixes, другие агенты, network/SUT/Docker/CI,
  TestOps записи, Git commit/push, live PR, checkout switching.
