# 20R — handoff: исправления приёмки оркестратора

Дата: 2026-11-15. **Статус: ready** — все пять дефектов исправлены,
локальная TestOps-цепочка реализована, проверки только offline
(fake runner/transports/git, tmp dirs). Live API/UI/SUT, Docker/Gradle,
CI, сеть, TestOps-публикации, commit/push/PR не выполнялись. Этап 20 и
полный MVP принятыми **не объявляются** — решение за координатором;
поручение 21 не начиналось.

## Результат

- Дизайн-документ: [20r-orchestrator-corrections.md](../design/20r-orchestrator-corrections.md).
- Изменённые модули: `infrastructure/workflow/adapters.py`,
  `orchestrator.py`, `tools/workflow.py`, `test_data/utils/workflow.py`.
- Новая регрессия: `tests/unit/test_workflow_20r.py` (32 кейса);
  обновлены `test_workflow_orchestrator.py` (F5 no-op в published),
  `test_workflow_intents.py` (assertion под durable-контракт F1).
- Runbook/каталог: `knowledge/integrations/qa-workflow.md`,
  `knowledge/components/workflow.md`.
- Evidence: `artifacts/workflow-implementation/20r-20261115T184327Z/`
  (`commands.md`, `historical-sha-{before,after}.txt`, `probe.py`,
  `probe-results.json` — копия исходного coordinator-вывода,
  `probe-results-after.json` — повторный прогон после исправлений).
- Probe координатора (`coordinator-20-review-20261115/probe.py`)
  прогнан повторно из temp dirs: все 5 случаев
  `violation_reproduced: false`. Исходные probe-файлы координатора
  восстановлены побайтно (sha256 совпадает с сохранённой копией).

## Входы и версии

- Среда (`sh tools/versions.sh`): Python 3.13.15, Selenium 4.51.0,
  pytest 9.1.1, allure-pytest 2.16.2, python-dotenv 1.2.1,
  psycopg 3.2.13.
- Принятые документы: поручение 20R, wave 20 целиком, задание/дизайн/
  handoff 20, wave 19, runbook qa-workflow и TestOps, каталог
  компонентов, `.agents/skills/run-tests/SKILL.md`.
- Приложение `niffler-py-st3` — только чтение, не изменялось.
- Защищённое состояние — SHA-256 до/после идентичны
  (`historical-sha-{before,after}.txt`): `artifacts/workflow/index.json`,
  `artifacts/workflow/wf-17431cddc9919d3d/state.json`, TestOps states
  `run-ni_5bvnc` / `run-5tsmzg1d` / `run-vzsatlfk`, `upload.log`,
  harness manifest `run-ni_5bvnc`. Чужие незакоммиченные изменения
  рабочего дерева сохранены.

## По дефектам

### F1 — unknown create не retry-safe

- Причина: reconcile по zero search переводил intent в failed →
  re-prepare/create повторяли внешнюю запись.
- Исправление: intent несёт immutable snapshot spec; reconcile читает
  spec из intent; zero search → unresolved+blocked; re-prepare/create
  при незавершённом intent — 69; inherited intents superseded линии
  блокируют ту же роль; revision/supersede intents не стирают.
- Регрессии: `TestF1UnresolvedExternalEffect` — полный путь create timeout → zero
  reconcile → changed prepare/revision/supersede → zero search →
  `create_calls == 1`; supersede-наследование; changed-spec guard.
- Evidence: probe `unknown_pr_reprepare_resends` — reprepare/second
  create blocked (69), create calls 1, `violation_reproduced: false`.

### F2 — единый preflight и строгая идентичность

- Причина: stale digest принимались как свежие; чужое evidence
  удовлетворяло executed по поверхностному manifest/bound_revision.
- Исправление: `_preflight`/`_require_fresh` перед всеми gate/mutation/
  effect-операциями + `doctor` read-only; строгие проверки manifest
  identity (tests commit, environment vs ревизия, source_identity vs
  checkout+copies, missing/changed_during_run пусты, container_check,
  состав JUnit/Allure по принятым сценариям); `--provenance` — единственный
  путь исторического baseline, с записью equivalence на execution.
- Регрессии: `TestF2PreflightAndIdentity` — drift requirements/tests/
  doc/sources/test_files между accept и следующим gate; doctor read-only;
  импорт — wrong tests commit, wrong app base при верном
  patch, missing source identity, changed current source, неверный
  image/scenario set; provenance waiver принят и записан.
- Evidence: probe `foreign_evidence_and_source_drift` — все попытки
  blocked, doctor показал implementation drift, `violation_reproduced:
  false`.

### F3 — проверяемый состав PR

- Причина: adoption по repo+branches+title_key принимал чужой PR; spec
  не нёс immutable head и полный digest.
- Исправление: `PrSpec.head_sha` (commit head → git SHA, patch head →
  digest патча, tests → tests commit, `--head-sha` override), полный
  title, `body_sha256`, `files`; `spec_sha256` — digest всего spec;
  adopt/verify только через `transport.get` + `pr_ref_exact` (точное
  совпадение title/head/body/files); spec без head_sha — локальный
  черновик, verified/published недостижимы.
- Регрессии: `TestF3ExactPrContent` — wrong/missing head/body/files/full
  title блокируются; положительный exact match → verified.
- Evidence: probe `unverified_pr_content_adopted` — adoption blocked
  (69), status blocked, spec с head_sha, `violation_reproduced: false`.

### F4 — классификация варианта

- Причина: commit-head manifest классифицировался base; противоречащие
  run-args проходили к dispatch.
- Исправление: `_manifest_variant` классифицирует относительно записанной
  ревизии (commit SHA == head → head; голый SHA без контекста — не
  доказанный base); `_manifest_matches_revision` требует base+patch для
  patch head и точный head SHA для commit head; `run_execution`
  отклоняет противоречия до dispatch.
- Регрессии: `TestF4VariantClassification` — base/patch/commit по обеим
  ревизиям; противоречащие args → 69; чужой commit-head → blocked.
- Evidence: probe `commit_head_classified_as_base` — variant `head`,
  совпал с current head, `violation_reproduced: false`.

### F5 — идемпотентный accept

- Причина: phase-gate срабатывал до проверки идемпотентности.
- Исправление: identical fresh artifact → `no-op` до phase-gate и любых
  runner/transport вызовов во всех фазах (включая published); изменённое
  содержимое той же ревизии → 69.
- Регрессии: `TestF5RepeatAccept` — все виды accept повторно,
  счётчики runner неизменны; changed-at-same-revision → 69; published
  identical → no-op.
- Evidence: probe `identical_accept_blocked` — second accept `no-op`,
  `violation_reproduced: false`.

### Локальная TestOps-цепочка

- `prepare-testops`: plan → assign → package через существующий
  `TestOpsAdapter`; каждый шаг durable в execution `state.json`; crash
  между шагами возобновляется с boundary; assign берёт mapping принятого
  bindings; execution с upload-статусом ≠ pending не пересобирается.
- `verify-testops --online`: возобновляемое подтверждение только из
  durable `sent` — повторный upload невозможен (`decide_upload` также
  отклонит resend); `uploaded` → no-op; durable `testops.verify` intent;
  `publish-testops` делегирует тот же `_dispatch_verify`.
- Регрессии: `TestLocalTestOpsChain` — crash после каждого шага с
  возобновлением без повтора выполненных шагов; sent→verify resume
  вызывает verify и **не** вызывает upload; uploaded → no-op;
  crash во время verify сохраняет resumable состояние.
- Offline только: `prepare-testops` без `--execute` (локальные writes в
  tmp-стор), verify за `--online`; live-поведение не проверялось.

## Собственные проверки (отдельно от проверок 20)

| Проверка | Результат |
| --- | --- |
| `.venv/bin/pytest tests/unit/test_workflow_20r.py -q` | 32 passed |
| `.venv/bin/pytest tests/unit/test_workflow_orchestrator.py tests/unit/test_workflow_intents.py -q` | 81 passed |
| Probe координатора (temp dirs) | exit 0, 5/5 `violation_reproduced: false` |
| `sh tools/compile-tests.sh` | 361 collected, exit 0 |
| `sh tools/run-tests.sh group unit` | 346 passed (`artifacts/harness/run-vu1p3zav/`) |
| `git diff --check` | clean |
| SHA защищённого state до/после | 7/7 идентичны |

## Ограничения

- Offline only: PR live-транспорта нет (77), TestOps upload/verify —
  gated (`--execute`/`--online`), их live-поведение не проверялось.
- Гарантия безопасности — «нет доказательства → blocked»; exactly-once
  на сервере не заявляется. Разрешение unresolved pr.create —
  remote-proof точного spec через reconcile либо ручное разбирательство.
- Исторический baseline импортируется только через явный
  `--provenance` с точными digest; без него gate остаётся blocked —
  проверки не ослаблены.
- Схема workflow state не менялась (schema-1); CLI harness
  (`run-tests.sh`/`compile-tests.sh`) и их публичная семантика не
  затрагивались.
- Общие workflow README/индекс/план MVP не изменялись — область
  координатора. Handoff/design/evidence 19/20 не тронуты.
