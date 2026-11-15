# Workflow-оркестратор (offline)

GitHub transport/body/CLI этапа 22 принят offline:
[wave 31](../../docs/qa-workflow/handoffs/coordination-wave-31.md).
Live GitHub и immutable heads этим не подтверждены.

[Оглавление каталога](README.md)

Минимальный CLI-оркестратор QA workflow (задачи 20 / 20R / 20R2): версированный
state, конверты артефактов, строгие versioned контракты источников, сценариев и
исторической baseline provenance, gate'ы фаз, durable checkpoints локальной
подготовки TestOps, lock'и, intents перед внешними вызовами и адаптеры к
существующим harness/TestOps helpers.
Runbook: [qa-workflow.md](../integrations/qa-workflow.md);
контракт: `docs/qa-workflow/design/19-orchestrator-contract.md`,
реализация: `docs/qa-workflow/design/20-orchestrator-implementation.md`,
исправления 20R: `docs/qa-workflow/design/20r-orchestrator-corrections.md`,
идентичность 20R2: `docs/qa-workflow/design/20r2-evidence-and-pr-identity.md`.

State живёт в `artifacts/workflow/<wf-id>/state.json` + общий
`artifacts/workflow/index.json`. Локальные `state.json` исторических
workflow — read-only evidence, не вход для новых прогонов.

## Точки входа

| Компонент | Путь / вызов | Назначение | Пример |
| --- | --- | --- | --- |
| Workflow CLI | `tools/run-workflow.sh` → `tools/workflow.py` | init/status/accept/check/run-execution/import-execution/prepare-testops/publish-testops/verify-testops/reconcile/resume/doctor/pr; коды 0/2/69/75/77/127/130; глобальный `--pr-transport {none,github}` | `sh tools/run-workflow.sh status` |
| `Orchestrator` | `infrastructure.workflow.orchestrator.Orchestrator` | Переходный автомат; `runner`, `git_adapter`, `tests_git_adapter`, `source_contract`, `scenario_contract` и `accepted_provenance` инъецируются только в тестах (боевой CLI использует пилотные контракты); `pr_transports` CLI подключает только при `--pr-transport github` и только на dispatch-командах (`pr create`, `pr search`, `reconcile`, `resume`) — lazy import + чистый конструктор без I/O, один объект в роли `app` и `tests` | `Orchestrator(root).init(pilot_id=..., ...)` |

Глобальные `--store-dir`/`--workflow-id`/`--pr-transport` идут до
subcommand (см. [runbook](../integrations/qa-workflow.md)): при >1
`wf-*/state.json` в
store флаг обязателен для всех команд — автовыбора active-линии по
`index.json` нет, разрешение сканирует директории
(`Orchestrator._resolve_workflow_id`). `init` выбирает линию по
`repo_key + pilot_id` и флаг не использует. `--pr-transport` сам по
себе сеть не разрешает: HTTP только при `--online`, POST — при
`--execute` + `--online` + действующие guard'ы.

## Схема и digest (`infrastructure.workflow.state`)

| Компонент | Назначение | Пример |
| --- | --- | --- |
| `new_state`, `load_state`, `save_state` | Schema-1 state, строгая валидация, атомарная запись tmp+fsync+replace | `state = load_state(workflow_dir)` |
| `validate_state`, `implied_phase` | Фаза выводится только из артефактов/executions/publications | `implied_phase(state)` |
| `workflow_id_for`, `normalize_repo_key` | Детерминированная идентичность `wf-<16 hex>`; repo key `host/path` без `.git` | `workflow_id_for(pilot, repo_key, base_sha)` |
| `bind_artifact`, `artifact_fresh`, `apply_revision` | Привязка digest зависимостей; T8 каскад stale | `apply_revision(state, data, reason)` |
| `executions_satisfy`, `execution_matches`, `publications_confirmed` | Gate'ы executions (scope api, bound revision) и публикаций (head execution `uploaded`, verified PR с immutable commit head `app_head.kind == "commit"` и clean `tests_repo`) | `executions_satisfy(state)` |
| `new_intent`, `set_intent`, `unfinished_intents`, `find_intent` | Журнал intents: declared→dispatched→completed/failed/unknown | `new_intent(state, "pr.create", target)` |
| `canonical_digest`, `sha256_file`, `require_git_sha`, `require_hex64` | Канонический JSON-digest и строгие проверки SHA | `canonical_digest(obj)` |
| Исключения `Workflow*Error` | `WorkflowError`→69, `WorkflowStateCorruptError`/`WorkflowSchemaError` (corrupt state), `WorkflowValidationError` (вход), `WorkflowBlockedError` (gate/lock), `WorkflowPermissionError`→77, `WorkflowLaunchError`→127 | `pytest.raises(WorkflowBlockedError)` |

## Контракты источников, сценариев и provenance (`infrastructure.workflow.contracts`)

| Компонент | Назначение | Пример |
| --- | --- | --- |
| `SourceContract`, `pilot_source_contract`, `required_source_paths` | Обязательный versioned allowlist `api-contract-v1` + принятые `implementation.test_files` | `required_source_paths(pilot_source_contract(), state)` |
| `validate_source_identity` | Проверка `contract_version`, пустых `missing`/`changed_during_run`, заполненного `rechecked_at`, уникальности/полноты путей, live/provenance sha256 и копий `sources/` | `validate_source_identity(contract, state, manifest, ev_dir, git, root)` |
| `ScenarioContract`, `pilot_scenario_contract`, `expected_variant_outcomes` | Точный контракт сценариев по вариантам (`head`: 6 passed, `base`: 4 ожидаемых негативных failed у пилота) и `ALLURE_ID` bindings | `pilot_scenario_contract()` |
| `validate_scenario_composition` | Строгая 1:1 биекция JUnit и raw Allure через `testops.results` (`load_results`, `validate_attachments`, `scan_assignments` по `fullName`+`parameters` без опоры на display title), сверка UUID, статусов и `ALLURE_ID` | `validate_scenario_composition(contract, "head", state, manifest, ev_dir)` |
| `DEFAULT_ACCEPTED_HISTORICAL_BASELINES`, `validate_historical_provenance_schema`, `verify_historical_baseline_acceptance` | Versioned schema v1 исторической baseline acceptance record: разрешена только для `base` из принятого реестра координатора, привязана к review-решениям на диске, exact SHA manifest/junit/allure и ограниченному `allowed_changed_files` с проверкой текущих SHA | `verify_historical_baseline_acceptance(record, ...)` |

## Конверты (`infrastructure.workflow.envelopes`)

| Компонент | Назначение | Пример |
| --- | --- | --- |
| `load_envelope`, `validate_envelope` | Строгий разбор envelope v1: actor ∈ {human,llm,orchestrator,imported}, document {path,sha256}, payload по виду артефакта | `env = load_envelope(path)` |
| `verify_document`, `artifact_digest` | Пересчёт sha256 документа и digest артефакта | `verify_document(root, env["document"])` |
| `validate_context_sources`, `validate_scenarios`, `validate_bindings` | Предметные проверки payload | `validate_scenarios(payload, ids)` |

## Адаптеры (`infrastructure.workflow.adapters`)

| Компонент | Назначение | Пример |
| --- | --- | --- |
| `SubprocessRunner`, `RunOutcome` | Запуск делегированных argv с построчным callback; `code`, `stdout`, `error` (launch_error/timeout/interrupted) | `runner.run(argv, cwd)` |
| `validate_argv` | Allowlist `sh tools/*` — произвольные команды из входов не выполняются | `validate_argv(argv)` |
| `GitReadAdapter` | Read-only git/file identity: `file_sha256`, `git_blob`, `head_commit`, `is_dirty`, а также проверка Git-объектов и дерева коммита `object_type`, `commit_file_bytes`, `commit_file_sha256`, `commit_blob`, `changed_files` | `GitReadAdapter(repo).object_type(sha)` |
| `snapshot_allowlist` | Детерминированный digest allowlist исходников для dirty checkout | `snapshot_allowlist(root, files)` |
| `HarnessAdapter` | `compile_args`, `list_args`, `api_run_args`, `run_collecting_evidence` (evidence dir сохраняется до завершения pytest) | `harness.api_run_args(app_patch_sha256=...)` |
| `TestOpsAdapter` | `plan/assign/package/upload/verify_args` + read-only `read_execution_state`, `execution_state_sha256`; execution state остаётся источником истины lifecycle | `adapter.upload_args(execution_id)` |
| `read_manifest`, `junit_summary`, `collected_node_ids` | Пересчёт evidence manifest/JUnit без доверия к exit code | `junit_summary(dir/"junit.xml")` |
| `PrTransport`, `PrRef`, `PrSpec`, `spec_digest`, `pr_ref_matches` | Протокол search/create/get для PR; candidate match repo+branches+title_key | `pr_ref_matches(ref, spec)` |
| `pr_ref_exact` | Verifiable match всего spec: полный title, immutable `head_sha`, digest тела и список файлов обязаны совпадать точно | `pr_ref_exact(ref, spec)` |
| `FakePrTransport` | Детерминированный транспорт со счётчиком вызовов для unit-тестов | `FakePrTransport(search_result=[ref])` |

## GitHub PR-транспорт (`infrastructure.workflow.github`, 22A/22AR)

Принятая в wave 30 stdlib-реализация `PrTransport`; подключается
боевым CLI только явным `--pr-transport github` и используется
неизменённо. Все сетевые вызовы ограничены `https://api.github.com`,
repo key строго `github.com/owner/repo`.

| Компонент | Назначение | Пример |
| --- | --- | --- |
| `GitHubPrTransport(token_provider=None, http=None)` | Lazy конструктор без I/O; `search(key)` — свежий list-запрос, `create(spec)` — ровно один POST (при частично читаемом ответе возвращает минимальный ref с number/url), `get(repo, number)` — detail → все страницы files → повторный detail со сверкой `SNAPSHOT_FIELDS` и точного `changed_files` | `transport.search(key)` |
| `EnvGitHubToken` | Default token provider: читает `GITHUB_TOKEN` только внутри authorized HTTP-вызова | `GitHubPrTransport()` |
| `UrllibHttp` | Default HTTP-слой поверх `HttpClient` без redirects; в тестах заменяется fake `request(endpoint, method, path, ...)` | инъекция `http=` |
| `GitHub*Error` | Контролируемые ошибки (`Spec`/`Auth`/`Http`/`Response`/`PrState`), наследники `WorkflowError` → CLI exit 69 | `pytest.raises(GitHubResponseError)` |

## Блокировки и index (`infrastructure.workflow.locks`, `index`)

| Компонент | Назначение | Пример |
| --- | --- | --- |
| `WorkflowLock`, `IndexLock` | O_EXCL lock-файлы поверх `ExecutionLock`: один writer на workflow и на `index.json`; мёртвый pid освобождается, битый lock отклоняется | `with WorkflowLock(dir):` |
| `load_index`, `save_index`, `register`, `find_entry`, `mark_active`, `acquire` | Журнал lineage repo+pilot → workflow; повторный init резюмит, иной base требует `--supersede` | `find_entry(index, repo_key, pilot)` |

## Тестовые helpers и константы

| Компонент | Путь импорта | Назначение | Пример |
| --- | --- | --- | --- |
| `C.*` | `test_data.consts.workflow` | Фиктивные SHA/ID, `UNIT_SCENARIO_INDEX`, `UNIT_DISPLAY_TITLES` и ожидания unit-тестов оркестратора; реальных данных и кредов нет | `project.init(app_base_sha=C.APP_BASE_SHA)` |
| `Project` | `test_data.utils.workflow` | Полный `api-contract-v1` QA-проект и app-checkout в tmp dir; методы класса: `init`, `envelope`/`*_envelope`, `commit_app_head`/`sync_tests_commit` (фиктивные Git-коммиты), `drive_to_implementation_ready`, `drive_to_executed`, `drive_commit_to_executed`, `publish_handlers`, `fake_pr_for` — методы класса, не модульные функции | `project.drive_commit_to_executed()` |
| `FakeRunner`, `FakeGit`, `unit_scenario_contract`, `default_source_files`, `snapshot_tree`, `write_manifest`, `write_raw_allure_results`, `write_allure_result`, `junit_case_name`, `scenario_names`, `make_testops_state`, `testops_local_handlers`, `harness_run`, `on_testops`, `set_upload_status` | `test_data.utils.workflow` | Модульные helpers: `FakeGit` с замороженными деревьями коммитов (`register_commit`), raw Allure JSON без scenario ID в `name`, локальная цепочка `plan/assign/package/upload/verify` поверх `build_package_verified` | `harness_run(runner, root, run_id, counts, 0)` |
| `SITECUSTOMIZE`, `SCENARIO_ENV`, `LOG_ENV`, `APP_REPO_KEY`, `TESTS_REPO_KEY`, `PR_*` | `test_data.consts.workflow_github_cli` | Фиктивные repo keys/payload и offline sitecustomize-bootstrap (fake HTTP rules + git trees через env-файлы) для subprocess-прогонов production CLI; реальных хостов/токенов нет | `_env(tmp_path, scenario)` в `test_workflow_github_cli.py` |

Все проверки оркестратора выполняются только в tmp dirs; исторические
`artifacts/testops/<execution>` и `artifacts/workflow*` репозитория в тестах
не трогаются.

## Семантика повторов и граница fake/live

- Повтор `verify-testops` на подтверждённом `uploaded` — `no-op`, но
  обновляет `last_observation.checked_at`/`state_sha256` в `state.json`:
  файл не бит-в-бит при повторах, тогда как identity digests
  (`workflow_id`, `revision_data`, executions, package/spec/state
  sha256, intent-идентификаторы) стабильны.
- `reconcile` и `resume` записывают локальный `state.json` (adopted
  outcomes, `last_observation`, журнал, refresh фазы): «read-only» в
  их описании относится к отсутствию повторных внешних эффектов
  (upload/create не повторяются), а не к собственному хранилищу.
- `check` — единственная команда на ранних фазах с реальным
  делегированным dispatch (`compile-tests.sh` + `run-tests.sh list`);
  `doctor` — только read-only отчёт целостности без dispatch и не
  является полным реальным прохождением цепочки.
- `published` в unit-пробах — результат `FakePrTransport`/`FakeRunner`
  simulation: боевой CLI подключает `GitHubPrTransport` только по
  явному `--pr-transport github` (проверено offline fake HTTP/git в
  `tests/unit/test_workflow_github_cli.py`, включая subprocess-прогоны
  настоящего `tools/workflow.py`), а реальный
  пилот (patch head + dirty tests) до immutable commit остаётся
  `executed`/pending. Fake `published` не доказывает live/MVP
  прохождение и не является приёмкой Git/PR этапа; поведение против
  живого GitHub API не проверялось.

## Проверка 21R и граница PR lineage

[Приёмка wave 25](../../docs/qa-workflow/handoffs/coordination-wave-25.md):
state/envelopes 21R-A приняты, документация 21R-C сверена с A/B кодом.
`validate_state` проверяет типы execution/strength requirements до
implied_phase; `publications_confirmed` требует ровно app/tests и
TestOps с `required is True`. Binding ID — положительный int без bool.

`Orchestrator.import_execution` для уже записанного base старой ревизии
возвращает `rebound` только после полной повторной проверки evidence;
сохраняет `rebound_from_revision` и событие `base-rebind`. Пример:
`orch.import_execution(execution_id)`; та же ревизия — `no-op`, прежний
head — `blocked`. Execution/source/provenance контракты не ослаблены.

21R-B добавил приватные `_reimport_recorded_execution`,
`_reprove_created_pr`, `_blocking_inherited`, `_refresh_inherited_intents`,
`_inherited_parent_verdict`. `_observe_testops(..., variant=None)`
резолвит вариант из executions и не заменяет head publication при base.
Reconcile сохраняет решения по intents по отдельности; report actions:
adopted/blocked/retryable/kept/error/ignored. CLI reconcile/resume
возвращают 0 также для controlled blocked/error report: читать содержимое
отчёта, не считать exit 0 доказательством resolution.

21R2 закрыл remaining guard: разрешение inherited intent больше не
теряет durable связь с известным remote effect. `init --supersede`
наследует также записанные в parent `inherited_intents` (unresolved
остаются блокерами, resolved хранят доказательство) и terminal
`pr.create` intents с записанным номером — как уже-resolved snapshot с
`resolved_in_parent`. `_inherited_parent_verdict` резолвит
`inherited_from` через `_ancestor_state` — обход записанной цепочки
`supersedes` (two-hop ancestry), чтение без lock'ов и fail-closed при
missing/corrupt/ambiguous. `pr_create` до свежего search и dispatch
вызывает `_reprove_lineage_pr` по номерам из `_lineage_pr_numbers`:
targeted get + `_verify_pr` к текущему spec; exact → adoption verified,
несовпадение/404 — blocked, ошибка get — unknown, автоматического
recreate нет ни в одной ветке. Регрессии: `tests/unit/test_workflow_21r2.py`.

Same-lineage created guard, base rebind, boundary-token implementation
gate, controlled error paths и PR lineage deduplication проверены на
offline-путях; общая приёмка 21/21R/21R2 оформлена в
[wave 26](../../docs/qa-workflow/handoffs/coordination-wave-26.md).
Live/MVP ограничения сохраняются. Константы `test_data.consts.workflow_21r_a`,
`workflow_21r_b` и `workflow_21r2` описаны в
[каталоге consts](consts.md); новые regression-файлы одноимённы в tests/unit.
