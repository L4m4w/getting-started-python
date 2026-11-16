# 21B — независимое ревью: external effects, recovery, PR/TestOps boundaries

Дата: 2026-11-15. Исполнитель: независимый ревьюер 21B (не автор 20/20R/20R2).
**Статус: `needs_decision`** — ревью завершено, все назначенные проверки
выполнены; зафиксировано **2 defect-level findings** (дублирующий PR create
при записанном `created` + пустом search; навсегда-блокирующий stale
inherited intent) и **5 minor findings**. Код не изменялся; другие агенты
не запускались; все операции offline, без сети/SUT/Docker/CI/live
TestOps/PR/git-commit.

Параллельные области: schema/state/evidence — 21A; index/locks/CLI/полная
цепочка — 21C. Этот отчёт покрывает только effect/recovery часть и **не**
является приёмкой задачи 21 или MVP. Boundary-наблюдения на стыках
помечены для координатора без дублирования чужих аудитов.

---

## 1. Проверенная версия (SHA)

Все 13 записей
`artifacts/workflow-implementation/coordinator-20r2-review-20261115/reviewed-inputs.sha256.json`
пересчитаны **до и после** ревью — полное совпадение, drift принятого кода
отсутствует.

Ключевые SHA-256 проверенной версии:

| Файл | SHA-256 (первые 16) |
| --- | --- |
| `infrastructure/workflow/orchestrator.py` | `19e506b9e88a5c7a` |
| `infrastructure/workflow/adapters.py` | `9a9b23a51227d1d3` |
| `infrastructure/workflow/state.py` | `a7c85ee1df724881` |
| `infrastructure/reporting/testops/lifecycle.py` | `a994e6854c05e44a` |
| `infrastructure/reporting/testops/state.py` | `55e132b2f13f00c3` |
| `tests/unit/test_workflow_intents.py` | `67dc26293563013d` |
| `tests/unit/test_workflow_20r.py` | `e1dab41af65c93a1` |
| `tests/unit/test_workflow_20r2.py` | `b86c4b8372785a75` |

Protected state/index/log/manifest: **19/19 OK** до и после
(`verification-summary.json::protected_sha_checks` координатора).
15/15 файлов `source_identity` manifest `run-ni_5bvnc` побайтово совпадают
с текущим checkout (`getting-started-python`, не `niffler-py-st3` —
источники лежат в этом репозитории). Результаты:
`artifacts/workflow-review/21b-20261115T201206Z/baseline-sha.json`,
`post-check-sha.json`.

## 2. Scope ревью

Effect/recovery в `orchestrator.py` (run/upload/verify/PR intents,
unknown reconciliation, spec snapshots, inherited intents,
supersede/revision, TestOps plan/assign/package checkpoints) и
`adapters.py` (PR transport protocol, `pr_ref_matches`/`pr_ref_exact`,
FakePrTransport). Плюс `testops/lifecycle.py::decide_upload` и
`testops/state.py` — как существующие guards, без запуска реальных
внешних операций.

## 3. Выполненные проверки (команды → exit → результат)

| Команда | Exit | Результат |
| --- | --- | --- |
| SHA сверка: 13 reviewed inputs | 0 | 13/13 до и после |
| SHA сверка: 19 protected (`protected_sha_checks`) | 0 | 19/19 до и после |
| SHA сверка: 15 `source_identity.files` из `run-ni_5bvnc` | 0 | 15/15 до и после |
| `pytest tests/unit/test_workflow_intents.py tests/unit/test_workflow_20r.py::TestF1UnresolvedExternalEffect ::TestF4VariantClassification tests/unit/test_workflow_20r2.py::TestR2GitHeadSeparation ::TestR4TestOpsCheckpoints --basetemp=<EV>/basetemp -o cache_dir=<EV> --junitxml=<EV>/results/assigned-tests.xml` | 0 | **57 passed** за 29.61s |
| `.venv/bin/python <EV>/probes.py <EV>/isolated-store` | 0 | 13 проб: 6 OK, **2 DEFECT**, 5 MINOR |

`<EV>` = `artifacts/workflow-review/21b-20261115T201206Z/`. Probe script,
stdout и JSON: `probes.py`, `probes.stdout.txt`,
`isolated-store/probe-results.json`. Изолированные stores: `probe-00..12`.

## 4. Findings по приоритету

### F1 (DEFECT, P1) — записанный `created` PR создаётся повторно при пустом search

- **Где:** `infrastructure/workflow/orchestrator.py:2262-2268`
  (guard-only `verified`/`blocked`), fall-through в dispatch
  `:2308-2357`; `entry["number"]` нигде не используется для targeted
  `transport.get()` перед повторным create (get() применяется только в
  `_verify_pr`, `:2448`).
- **Триггер:** `transport.create` вернул читаемый ref, но `_verify_pr`
  дал False → `entry.status="created"`, `entry.number` записан. Позже
  `pr_create` вызван повторно; свежий `transport.search` вернул `[]`
  (lag индекса, окно видимости, фильтрация) → `matching` пуст →
  `len(found) > len(matching)` ложно → код доходит до `:2347` и шлёт
  второй `transport.create(spec)`.
- **Последствие:** дублирующий внешний эффект — в fake-пробе
  `remote_pr_count=2`, номера `[100, 101]`. Нарушает контракт 20R
  «никаких повторных внешних эффектов без точного доказательства» —
  но для статуса `created`, а не `unknown` (для `unknown` блокировка
  работает, см. P3).
- **Repro:** `probes.py::probe_created_pr_zero_search_recreates` (P1);
  контроль P2 показывает, что когда search PR видит — adoption
  корректен (`remote_pr_count=1`, `verified`).
- **Корень асимметрии:** `_reconcile_pr` (`:1880+`) корректно держит
  intent blocked при пустом search, но `pr_create` — отдельный путь —
  считает `created`+пустой search основанием для нового dispatch.

### F2 (DEFECT, P9) — stale inherited intent навсегда блокирует новую lineage

- **Где:** `orchestrator.py:2369-2380` (`_inherited_pr_intents` читает
  только snapshot `state["inherited_intents"]`), блокировки в
  `pr_prepare` `:2148-2154` и `pr_create` `:2281-2287`.
- **Триггер:** supersede копирует незавершённые PR intents старой
  lineage в `inherited_intents` один раз. Если в старой workflow intent
  позже разрешён (reconcile → `adopted`, status `verified`), snapshot в
  новой lineage не обновляется — остаётся `unknown`.
- **Последствие:** `pr_prepare`/`pr_create` в новой lineage возвращают
  `blocked` бессрочно («resolve it in the superseded workflow first»),
  хотя оно уже resolved. Нет пути refresh/clear — только ручная
  правка state. Recovery dead-end.
- **Repro:** `probes.py` P9: `reconcile_old='adopted'`,
  `old_status='verified'`, `inherited_statuses=['unknown']`,
  `new_prepare='blocked'`.
- **Примечание:** сама блокировка по незавершённому inherited intent —
  корректный дизайн; дефект — отсутствие механизма пере-сверки с
  superseded workflow.

### F3 (MINOR, P6) — KeyError при reconcile intent без spec

- **Где:** `orchestrator.py:1891-1894` → `adapters.py:457`
  (`pr_ref_matches` индексирует `spec["repo"]`).
- **Триггер:** dispatched `pr.create` intent без `target.spec` и
  `entry` без spec (`spec=None`) → `pr_ref_matches(ref, {})` →
  `KeyError: 'repo'`. Reconcile умирает на всём цикле; ранние in-memory
  решения не сохранены (единственный `save_state` на `:1808`).

### F4 (MINOR, P6b) — transport.search exceptions не классифицированы

- **Где:** `orchestrator.py:1892` (reconcile) и `:2309` (pr_create
  pre-dispatch search). `transport.create` обёрнут в try/except
  (`:2384-2401`), `search` — нет.
- **Триггер:** search backend бросает исключение → оно уходит наружу из
  `reconcile()`/`pr_create()` как stack trace. Intent остаётся
  `dispatched` (консервативно — это плюс), но оператор получает
  неклассифицированный crash вместо controlled unknown/blocked.

### F5 (MINOR, P7/P7b) — StateCorruptError обработан непоследовательно

- **Где:** `publish_testops` ловит (`:1684-1689` → blocked-69);
  `verify_testops` (`:1572`), `_reconcile_upload` (`:1850`) и
  `_observe_testops` (`:1226`, вызовы `:1578/:1626/:1757/:1806/:1854`)
  — нет. `StateCorruptError` — plain `Exception`, не `WorkflowError`.
- **Триггер:** corrupt `artifacts/testops/<exec>/state.json` →
  `verify_testops` и `reconcile` падают с raw exception; reconcile
  теряет все предыдущие решения цикла (save на `:1808` не достигается).
  Probe: `verify_testops: crash:StateCorruptError`,
  `prepare_testops/publish_testops: blocked-69`, `import: no-error`.

### F6 (MINOR, P8) — observation base execution перезаписывает head publication

- **Где:** `_observe_testops` `:1224-1239`; guard `variant=="base"`
  (`:1230-1233`) передаётся только из import (`:1185`). Вызовы из
  verify/reconcile (`:1578/:1626/:1757/:1806/:1854`) — `variant=None`.
- **Триггер:** `verify_testops`/`reconcile` для base execution →
  `pubs["execution_id"]` и `last_observation` переписываются данными
  base (`run-unitbase1` вместо `run-unithead1`).
- **Последствие:** `phase` остаётся `executed`, upload не повторяется;
  загрязняется provenance `publications.testops` — observation больше
  не описывает head-публикацию. Минорный, но искажает evidence для
  recovery.

## 5. Подтверждённые безопасные поведения (probe OK)

| Probe | Результат |
| --- | --- |
| P2 created+search видит PR | `adopted`, remote=1, final `verified` |
| P3 unknown PR intent | re-prepare/create@rev2/reconcile/superseded-lineage — все `blocked`, create dispatches=1 |
| P4 sent/unknown/in_progress/uploaded/failed | все `blocked` до transport; testops-calls=0 |
| P4b unconfirmed verify | `unconfirmed`, exit 75, upload=0, повторный publish `blocked` |
| P5 prepare crash boundaries | crash после plan→resume: assign+package; после assign→package; после package→no-op; готовые шаги не повторяются (0 re-dispatch) |
| P10 run crash before save | reconcile `adopted` по evidence manifest, pytest dispatches=1 |

P3 покрывает все четыре требуемых пути: повторный prepare, create после
revision bump, reconcile, prepare в superseded lineage — unknown intent
надёжно блокирует повторный create.

## 6. Проверенное vs непроверенное

**Проверено (offline, fake transport/runner):**
- Run/upload/verify/PR intents — declared/dispatched/unknown/completed
  жизненный цикл, crash до/после persisted intent, crash после успеха
  fake subprocess до save.
- TestOps decide_upload guards для всех indeterminate статусов.
- Prepare checkpoints plan/assign/package — crash-resume без повторов.
- PR spec snapshot в intent, adoption по exact spec, ambiguous/foreign
  search → blocked.
- Empty PR search для `unknown` intent → blocked (не retry).
- **Не покрыто безопасным поведением:** `created` + empty search (F1),
  inherited-intent refresh (F2).

**Не проверено:**
- Live transport: реальный GitHub/GitLab search lag, `get(number)`
  семантика, rate limits — только FakePrTransport.
- Реальные subprocess crashes (только fake runner raise).
- Real git repos/SHAs (FakeGit), real TestOps API, network.
- Live PR publication boundary — как и принятый 20R2, это offline-only
  verification; F1 показывает, что даже fake-уровень выявляет дыру в
  дедупликации.

## 7. Ограничения live transport и рекомендации для Git/PR пакета

1. **F1 (блокирующее для live PR):** перед любым `transport.create`
   при `entry.status=="created"` и `entry.number is not None` — обязателен
   targeted `transport.get(repo, number)` + `pr_ref_exact`; found →
   adopt/verify, 404 → только тогда рассмотреть create с decision
   record, transport error → blocked. Иначе search lag даст
   настоящие дубли PR.
2. **F2:** reconcile/resume должен пере-сверять `inherited_intents` со
   state superseded workflow (или дать explicit resolve/clear path).
3. **F4:** обернуть `transport.search` в классификацию (unknown/blocked)
   в обоих путях — `:1892` и `:2309`.
4. **F5:** единообразно ловить `StateCorruptError` в verify/reconcile/
   observe → blocked-69.
5. **F6:** передавать variant в `_observe_testops` из verify/reconcile
   либо не трогать `pubs` для не-head executions.
6. **F3:** guard `spec is None` перед `pr_ref_matches` → keep/blocked
   вместо KeyError.
7. Live Git/PR пакет не готов к публикации: F1 — реальный дубликат
   внешнего эффекта при первом же search-lag; F2 — dead-end восстановления
   после supersede. Оба требуют решения координатора до live-прогона.

## 8. Evidence

`artifacts/workflow-review/21b-20261115T201206Z/`:
`baseline-sha.json`, `post-check-sha.json`, `results/assigned-tests.xml`,
`probes.py`, `probes.stdout.txt`,
`isolated-store/probe-results.json`, `isolated-store/probe-00..12`,
`basetemp/`, `pycache/`.

После handoff останавливаюсь до объединённой приёмки координатором.
