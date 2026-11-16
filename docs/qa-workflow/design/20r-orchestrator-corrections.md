# Исправления приёмки оркестратора (20R)

Дата: 2026-11-15. Статус: реализовано и проверено offline (fake
transports/runner, временные проекты); live-операции не выполнялись.
Основание: [поручение 20R](../agent-tasks/20r-orchestrator-corrections.md),
пять воспроизведённых координатором дефектов из
[wave 20](../handoffs/coordination-wave-20.md) и probe
`artifacts/workflow-implementation/coordinator-20-review-20261115/`.
База реализации: [20](20-orchestrator-implementation.md). Схема state не
менялась (schema-1); изменения — поведение и контракты.

## 1. F1 — неизвестный исход pr.create и immutable intent

**Дефект.** Dispatched `pr.create` при zero search помечался failed и
становился retry-safe; re-prepare/revision/supersede перезаписывали spec
и стирали запись о внешнем эффекте — повторный create удваивал публикацию.

**Исправление.**

- `Orchestrator._dispatch_pr_create` замораживает в intent
  (`target.spec`) полный snapshot spec на момент dispatch; reconciliation
  читает spec только из intent, а не из текущей записи publications.
- `_reconcile_pr`: точный match через свежий search + `transport.get` +
  `pr_ref_exact` → adopt/verified; ноль результатов → intent остаётся
  unresolved (`unknown`/`dispatched`), entry `blocked` — пустой поиск
  никогда не доказывает отсутствие эффекта; неполные/чужие кандидаты →
  blocked.
- `pr_prepare` и `pr_create` блокируются (исход `blocked`, exit 69), пока
  для той же роли существует незавершённый create-intent — в текущей
  записи и среди `inherited_intents` superseded линии
  (`_inherited_pr_intents`). Revision/supersede не стирают intents
  (`apply_revision` переносит их как unfinished).
- Флагов reset/force не добавлено: разрешение — только remote-proof
  точного spec или ручное разбирательство оператора.

## 2. F2 — единый preflight и строгая идентичность evidence

**Дефект.** Принятые артефакты не перепроверялись: изменение файлов после
accept проходило по записанным digest; import принимал чужое evidence по
поверхностному manifest, `bound_revision` считался доказательством.

**Исправление.**

- `Orchestrator._preflight(state)` — единый read-only пересчёт: документ
  requirements, tests commit/dirty/snapshot против checkout, документы
  принятых артефактов, context sources против app checkout, записанные
  `test_files_sha256` implementation. Вызывается перед каждым gate/
  mutation/effect (`_require_fresh` → `WorkflowBlockedError`):
  `accept`, `run_execution`, `import_execution`, `prepare_testops`,
  `publish_testops`, `verify_testops`, `pr_prepare`, `pr_create`.
  `doctor` выводит тот же список проблем без мутаций.
- `import_execution` / `_adopt_run_evidence` — строгие проверки
  (`_manifest_problems`, `_source_identity_problems`,
  `_environment_problems`, `_composition_problems`): tests commit+dirty
  против записанного repo, environment (base+patch либо точный head SHA)
  против ревизии, `source_identity` — digest каждого файла против
  checkout и копий в evidence, `missing`/`changed_during_run` пусты,
  обязательный container_check при объявленном image, состав JUnit/Allure
  — только принятые сценарии. Нарушение → blocked-исход, execution не
  записывается.
- Исторический baseline допускается только через явный
  `--provenance <file.json>` (keys `tests_commit`, `tests_dirty`,
  `sources`, `source_identity_missing`): каждое поле должно совпасть с
  manifest и записывается на execution. Подстановка current SHA в старый
  manifest невозможна; без provenance строгий импорт честно блокируется.

## 3. F3 — проверяемый состав PR

**Дефект.** Search key repo+branches+`[wf-id]` принимал чужой PR;
`spec_sha256` не покрывал содержимое; immutable head отсутствовал —
verified достигался по частичному совпадению.

**Исправление.**

- `PrSpec`/`PrRef` расширены `head_sha`, `body_sha256`, `files`
  (`adapters.py`); `spec_sha256` — canonical digest всего spec
  (`spec_digest`).
- `Orchestrator._pr_head_sha`: app — git SHA при commit head, digest
  патча при patch head (не-git объект, транспорт обязан отразить его в
  `ref.head_sha`); tests — записанный tests commit. `--head-sha` —
  явное переопределение.
- `adapters.pr_ref_exact`: verifiable match — полный title, immutable
  `head_sha`, digest тела и список файлов равны spec точно; spec без
  `head_sha` верифицировать нельзя (черновик, не публикация).
  `pr_ref_matches` остаётся только отбором кандидатов.
- `_verify_pr` подтверждает через `transport.get(repo, number)` +
  `pr_ref_exact`; adopt/create без exact match → created не переводится
  в verified, неоднозначность → blocked.

## 4. F4 — классификация варианта относительно ревизии

**Дефект.** Manifest с `app_base_sha`, равным head-commit, классифицировался
base; противоречащие run-args (head+patch без base и т.п.) доходили до
dispatch.

**Исправление.**

- `_manifest_variant(manifest, identity, revision_data)`: patch в
  environment → head; `app_base_sha` == записанному commit head → head;
  base — только когда SHA доказанно равен `identity.app_base_sha`.
  Без контекста ревизии голый SHA консервативно считается head — он ещё
  должен доказать точный head в `_manifest_matches_revision` (probe
  вызывает `_manifest_variant(manifest)` одним аргументом).
- `_manifest_matches_revision`: base связывается только immutable
  `identity.app_base_sha`; patch-head требует base И patch;
  commit-head — точный `head.git_sha` без patch.
- `run_execution` до dispatch валидирует согласованность запрошенного
  variant с записанной ревизией (head-args против kind ревизии;
  противоречие base/patch → 69 до intent dispatch).

## 5. F5 — идемпотентный accept

**Дефект.** Повторный accept идентичного свежего envelope в поздних фазах
блокировался phase-gate до проверки идемпотентности.

**Исправление.** `accept` сначала разбирает envelope и сравнивает digest с
принятым артефактом той же ревизии: идентичный и свежий →
`{"outcome": "no-op"}` до phase-gate, compile/list и любых runner/
transport вызовов — во всех фазах, включая `published`. Изменённое
содержимое при той же ревизии → 69 (требуется новый input revision);
новый артефакт проходит gates как раньше. Идемпотентность определяется
сравнением содержимого, а не одним envelope digest.

## 6. Локальная TestOps-цепочка и возобновляемый verify

- `Orchestrator.prepare_testops(execution_id)` — plan → assign →
  package через `TestOpsAdapter` (`run-testops.sh` argv): каждый шаг
  durable записывается execution state TestOps, крах между шагами
  возобновляется с persisted boundary; assign получает mapping из
  принятого bindings; выполненные шаги не повторяются (idempotent
  delegated CLI); execution с upload-статусом ≠ pending не пересобирается.
- `Orchestrator.verify_testops(execution_id, online)` — отдельный шаг
  подтверждения: разрешён только из durable `sent` (повторный upload
  исключён — `decide_upload` также откажет в resend), `uploaded` → no-op,
  прочие статусы → blocked. Работает под durable `testops.verify` intent;
  verify — идемпотентное чтение, незавершённый intent может быть
  перевыпущен.
- `publish_testops` делегирует подтверждение общему
  `_dispatch_verify` — единый путь upload → sent → verify.
- `tools/workflow.py`: действия `prepare-testops` и
  `verify-testops --online`; `pr create` принимает `--head-sha`.
- Наблюдение статусов через `_observe_testops` отражается в
  `publications.testops` workflow state.

## 7. Тестовые изменения

- `tests/unit/test_workflow_20r.py` (32 кейса): каждый дефект — полный
  путь координаторского воспроизведения (F1: create-timeout → zero
  reconcile → re-prepare/revision/supersede → zero search → create count
  остаётся 1), crash boundary каждого шага TestOps-цепочки и resume
  sent→verify без повторного upload.
- `test_data/utils/workflow.py`: `FakeGit` (deterministic HEAD/dirty для
  не-git checkout), строгие manifests с полной source/environment
  identity, `write_allure_result` + `scenario_names` (Allure-кейсы по
  именам сценариев), `testops_local_handlers` (fake plan/assign/package/
  upload/verify с записью в tmp-стор), полные `PrRef` фикстуры.
- `tests/unit/test_workflow_orchestrator.py`: published + identical
  accept → no-op (контракт F5).
- `tests/unit/test_workflow_intents.py`: zero-search reconcile оставляет
  injected dispatched intent unresolved (assertion исправлена на
  фактический durable статус).

## 8. Ограничения

Live-транспорта PR нет (CLI `search`/`create` — 77); TestOps upload
за `--execute`, verify за `--online`. Exactly-once на сервере не
гарантируется: гарантия — «нет доказательства → blocked». Live-проверки,
UI/SUT, Docker/Gradle, CI и реальные writes не выполнялись.
